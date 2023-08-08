import asyncio
import contextvars
import functools
import traceback
from asyncio import Condition, create_task, events, gather
from asyncio import sleep as asyncio_sleep
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from logging import getLogger
from typing import Callable, Collection, List, Optional, Tuple

from rate_limited.calls import Call
from rate_limited.progress_bar import ProgressBar
from rate_limited.queue import CompletionTrackingQueue
from rate_limited.resources import Resource, Unit


class Runner:
    def __init__(
        self,
        function: Callable,
        resources: Collection[Resource],
        max_concurrent: int,
        max_retries: int = 0,
        progress_interval: float = 1.0,
    ):
        self.function = function
        self.resource_manager = ResourceManager(resources)
        self.max_concurrent = max_concurrent
        self.requests_executor_pool = ThreadPoolExecutor(max_workers=max_concurrent)
        self.max_retries = max_retries
        self.progress_interval = progress_interval
        # TODO: add verification functions?
        # (checking if response meets criteria, retrying otherwise)

        self.logger = getLogger(f"rate_limited.Runner.{function.__name__}")

        # list of all calls that have been scheduled, in order of scheduling
        self.scheduled_calls: List[Call] = []
        # queue of calls to be executed in the current run()/run_coro() call, including retries
        # (needs to be initialized in the context of the event loop we will execute in)
        self.execution_queue: Optional[CompletionTrackingQueue] = None

        self.interrupted = False

    def schedule(self, *args, **kwargs):
        # TODO: use docstring from self.function?
        call = Call(self.function, args, kwargs)
        if not self.resource_manager.is_call_allowed(call):
            raise ValueError(f"Call {call} exceeds resource quota - will never be executed")
        self.scheduled_calls.append(call)
        if self.execution_queue is not None:
            self.execution_queue.put_nowait(call)

    async def worker(self):
        assert self.execution_queue is not None
        while not self.interrupted:
            # wait to get a task
            call = await self.execution_queue.get()
            # wait for resources to be available
            await self.resource_manager.wait_for_resources(call)

            # starting to execute - but first, register the usage
            self.resource_manager.register_call(call)
            self.resource_manager.pre_allocate(call)
            try:
                # TODO: add a timeout mechanism?
                call.result = await self.to_thread_in_pool(self.function, *call.args, **call.kwargs)
                # TODO: are there cases where we need to register result-based usage on error?
                # (one case: if we have user-defined verification functions)
                self.resource_manager.register_result(call.result)
            except Exception as e:
                will_retry = call.num_retries < self.max_retries
                self.logger.warning(
                    f"Exception occurred, will retry: {will_retry}\n{traceback.format_exc()}"
                )
                call.exceptions.append(e)
                if will_retry:
                    call.num_retries += 1
                    self.execution_queue.put_nowait(call)
            finally:
                self.resource_manager.remove_pre_allocation(call)
                self.execution_queue.task_done()

    async def to_thread_in_pool(self, func, /, *args, **kwargs):
        """Copy of asyncio.to_thread, but:
        - using a custom thread pool
        - not requiring Python 3.9
        - cancelling the future when the task is cancelled

        Asynchronously run function *func* in a separate thread.

        Any *args and **kwargs supplied for this function are directly passed
        to *func*. Also, the current :class:`contextvars.Context` is propagated,
        allowing context variables from the main thread to be accessed in the
        separate thread.

        Return a coroutine that can be awaited to get the eventual result of *func*.
        """
        loop = events.get_running_loop()
        ctx = contextvars.copy_context()
        func_call = functools.partial(ctx.run, func, *args, **kwargs)
        future = loop.run_in_executor(self.requests_executor_pool, func_call)
        try:
            return await future
        except asyncio.CancelledError:
            future.cancel()  # TODO: this is just a precaution, should not be needed, remove?
            raise

    def initialize_in_event_loop(self):
        """
        Needs to be called once we are in the context of the (current) event loop.

        Note: If called multiple times (via run()) the event loop will be different -
        we need to re-initialize the synchronization primitives.
        """
        # NB: (re-)initializing asyncio synchronization primitives not needed for newer Python
        # versions (>=3.10?) - but queue cleanup still needed
        self.resource_manager.initialize_in_event_loop()
        self.execution_queue = CompletionTrackingQueue()
        for call in self.scheduled_calls:
            if call.result is None and call.num_retries <= self.max_retries:
                self.execution_queue.put_nowait(call)

    async def run_coro(self) -> Tuple[list, list]:
        """
        Actual implementation of run() - to be used by run() and run_sync()
        """
        self.interrupted = False
        self.initialize_in_event_loop()
        assert self.resource_manager.condition is not None  # for mypy's benefit
        assert self.execution_queue is not None

        worker_tasks = [create_task(self.worker()) for _ in range(self.max_concurrent)]

        pbar = ProgressBar(total=len(self.scheduled_calls))
        while not self.execution_queue.all_tasks_done() and not self.interrupted:
            num_completed = self.execution_queue.tasks_done_count
            self.logger.debug(f"Tasks done: {num_completed} interrupted: {self.interrupted}")
            pbar.set_state(num_completed, num_total=self.execution_queue.all_tasks_count)
            # TODO: use a condition/signal instead? though OS support varies
            # NB: KeyboardInterrupt handling will wait for this sleep too - should not be too long
            await asyncio_sleep(self.progress_interval)
            if not self.interrupted:
                async with self.resource_manager.condition:
                    self.resource_manager.wake_workers()
        pbar.set_state(self.execution_queue.tasks_done_count)
        pbar.close()
        self.logger.debug("Done processing - cancelling worker tasks")
        for task in worker_tasks:
            task.cancel()
        await gather(*worker_tasks, return_exceptions=True)
        self.logger.info("Workers finished")
        results = [call.result for call in self.scheduled_calls]
        exception_lists = [call.exceptions for call in self.scheduled_calls]
        if not self.interrupted:
            self.scheduled_calls = []  # only clear the queue if returning complete results
        # TODO: consider returning a generator, instead of waiting for all calls to finish?
        return results, exception_lists

    def _run_sync(self) -> Tuple[list, list]:
        """
        Execute run_coro() from sync code - starting a new event loop
        """
        return asyncio.run(self.run_coro())

    def run(self) -> Tuple[list, list]:
        """
        Runs the scheduled calls, returning a tuple of:
        - results (list, in order of scheduling) and
        - exceptions(list of lists, in order of scheduling)

        Can be called from both sync and async code
        (so that the same code can be used in a script and a notebook - Jupyter runs an event loop)
        """
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(self._run_sync)
            try:
                return future.result()
            except KeyboardInterrupt:
                self.logger.warning("Interrupted, collecting already returned results")
                self.interrupted = True
                return future.result()


class ResourceManager:
    def __init__(self, resources: Collection[Resource]):
        self.resources = list(resources)
        self.condition: Optional[Condition] = None
        self.logger = getLogger("rate_limited.ResourceManager")

    def initialize_in_event_loop(self):
        if self.condition is None:
            self.condition = Condition()
            return

        current_loop = asyncio.get_running_loop()
        if self.condition._loop is not current_loop:
            # new event loop -
            self.logger.debug("Detected event loop change - re-initializing condition")
            self.condition = Condition()

    def is_call_allowed(self, call: Call) -> bool:
        """
        Checks if the resources needed are below the quota - otherwise it will never be allowed
        """
        for resource in self.resources:
            needed = Unit(0)
            if resource.arguments_usage_extractor is not None:
                needed += resource.arguments_usage_extractor(call)
            if resource.max_results_usage_estimator is not None:
                needed += resource.max_results_usage_estimator(call)
            if needed > resource.quota:
                return False
        return True

    def register_call(self, call: Call):
        for resource in self.resources:
            if resource.arguments_usage_extractor:
                resource.add_usage(resource.arguments_usage_extractor(call))

    def pre_allocate(self, call: Call):
        for resource in self.resources:
            if resource.max_results_usage_estimator:
                resource.reserve_amount(resource.max_results_usage_estimator(call))

    def register_result(self, result):
        for resource in self.resources:
            if resource.results_usage_extractor:
                resource.add_usage(resource.results_usage_extractor(result))

    def remove_pre_allocation(self, call: Call):
        # Right now assuming that pre-allocation is only based on the call, this could change
        # to e.g. be also based on history of results
        for resource in self.resources:
            if resource.max_results_usage_estimator:
                resource.remove_reserved(resource.max_results_usage_estimator(call))

    def get_next_usage_expiration(self) -> datetime:
        return min(resource.get_next_expiration() for resource in self.resources)

    def _has_space_for_call(self, call: Call) -> bool:
        # important - we should NOT have any async code here!
        # (because we are inside a condition check)
        for resource in self.resources:
            needed = Unit(0)
            if resource.arguments_usage_extractor is not None:
                needed += resource.arguments_usage_extractor(call)
            if resource.max_results_usage_estimator is not None:
                needed += resource.max_results_usage_estimator(call)
            if not resource.is_available(needed):
                self.logger.debug(f"resource {resource.name} is not available: {resource}")
                return False
        self.logger.debug("all resources are available")
        return True

    async def wait_for_resources(self, call: Call):
        assert self.condition is not None
        async with self.condition:
            await self.condition.wait_for(lambda: self._has_space_for_call(call))

    def wake_workers(self):
        assert self.condition is not None
        # TODO: this is too eager, we could only wake a subset of workers
        # (exact solution non-trivial?, gains likely negligible)
        self.condition.notify_all()
