import asyncio
import traceback
from asyncio import create_task, gather
from asyncio import sleep as asyncio_sleep
from concurrent.futures import ThreadPoolExecutor
from inspect import signature
from logging import getLogger
from typing import Callable, Collection, List, Optional, Tuple

from rate_limited.calls import Call
from rate_limited.progress_bar import ProgressBar
from rate_limited.queue import CompletionTrackingQueue
from rate_limited.resource_manager import ResourceManager
from rate_limited.resources import Resource
from rate_limited.threading_utils import to_thread_in_pool


class Runner:
    def __init__(
        self,
        function: Callable,
        resources: Collection[Resource],
        max_concurrent: int,
        max_retries: int = 5,
        progress_interval: float = 1.0,
        long_wait_warning_seconds: Optional[float] = 2.0,
    ):
        self.function = function
        self.resource_manager = ResourceManager(resources)
        self.max_concurrent = max_concurrent
        self.requests_executor_pool = ThreadPoolExecutor(max_workers=max_concurrent)
        self.max_retries = max_retries
        self.progress_interval = progress_interval
        self.long_wait_warning_seconds = long_wait_warning_seconds
        # TODO: add verification functions?
        # (checking if response meets criteria, retrying otherwise)

        self.logger = getLogger(f"rate_limited.Runner.{function.__name__}")

        # list of all calls that have been scheduled, in order of scheduling
        self.scheduled_calls: List[Call] = []
        # queue of calls to be executed in the current run()/run_coro() call, including retries
        # (needs to be initialized in the context of the event loop we will execute in)
        self.execution_queue: Optional[CompletionTrackingQueue] = None
        self.interrupted = False

        self._update_schedule_as_wrapper(function)

    def schedule(self, *args, **kwargs) -> None:
        """
        Use to schedule a call to the function

        If the normal call looked liked `my_function("some text", temperature=0.5)`, then
        `runner.schedule("some text", temperature=0.5)` should be used instead.
        """
        call = Call(self.function, args, kwargs)
        if not self.resource_manager.is_call_allowed(call):
            raise ValueError(f"Call {call} exceeds resource quota - will never be executed")
        self.scheduled_calls.append(call)
        if self.execution_queue is not None:
            self.execution_queue.put_nowait(call)

    def run(self) -> Tuple[list, list]:
        """
        Runs the scheduled calls, returning a tuple of:
        - results (list, in order of scheduling) and
        - exceptions(list of lists, in order of scheduling)

        Can be called from both sync and async code
        (so that the same code can be used in a script and a notebook - Jupyter runs an event loop)

        Handles KeyboardInterrupt (SIGINT) gracefully by returning partial results.
        """
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(self._run_sync)
            try:
                return future.result()
            except KeyboardInterrupt:
                self.logger.warning("Interrupted, collecting already returned results")
                self.interrupted = True
                return future.result()

    def _run_sync(self) -> Tuple[list, list]:
        """
        Execute run_coro() from sync code - starting a new event loop
        """
        return asyncio.run(self.run_coro())

    async def run_coro(self) -> Tuple[list, list]:
        """
        Coroutine actually implementing the execution of the scheduled calls

        Can be used directly from async code (e.g. in a Jupyter notebook):
        ```
        results, exceptions = await runner.run_coro()
        ```
        or indirectly via run() - from any environment:
        ```
        results, exceptions = runner.run()
        ```
        """
        self.interrupted = False
        self.initialize_in_event_loop()
        assert self.resource_manager.condition is not None  # for mypy's benefit
        assert self.execution_queue is not None

        worker_tasks = [create_task(self.worker()) for _ in range(self.max_concurrent)]

        pbar = ProgressBar(
            total=len(self.scheduled_calls), long_wait_seconds=self.long_wait_warning_seconds
        )
        while not self.execution_queue.all_tasks_done() and not self.interrupted:
            num_completed = self.execution_queue.tasks_done_count
            self.logger.debug(f"Tasks done: {num_completed} interrupted: {self.interrupted}")
            pbar.set_state(num_completed, num_total=self.execution_queue.all_tasks_count)

            # all workers waiting for resources and no usage expires soon -> show a warning
            next_progress_estimate = (
                self.resource_manager.get_next_usage_expiration()
                if self.resource_manager.num_waiting_for_resources == self.max_concurrent
                else None
            )
            pbar.update_long_wait_warning(
                next_progress_estimate, "All workers waiting for resources"
            )

            # TODO: use a condition/signal instead? though OS support varies
            # NB: KeyboardInterrupt handling will wait for this sleep too - should not be too long
            await asyncio_sleep(self.progress_interval)
            if not self.interrupted:
                # wake up waiting workers - perhaps now resources are available
                await self.resource_manager.notify_waiting()
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
                call.result = await to_thread_in_pool(
                    self.requests_executor_pool, self.function, *call.args, **call.kwargs
                )
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

    def _update_schedule_as_wrapper(self, function):
        """
        Update the schedule() method to have a useful signature and docstring as the wrapped
        function.
        """
        # TODO: consider more robust wrapper behavior, support VS Code better - maybe using `wrapt`

        qualname = getattr(function, "__qualname__")
        name = getattr(function, "__name__")
        module = getattr(function, "__module__")
        orig_docstring = getattr(function, "__doc__") or "[Docstring not found]"
        signature_rendered = str(signature(function))

        new_docstring = (
            f"Schedule a call to {qualname} in {module}\n"
            "Returns None - call run() to get results\n\n"
            f"{name}{signature_rendered}\n"
            f"Docstring:\n\n"
            f"{orig_docstring}"
        )
        self.schedule.__func__.__doc__ = new_docstring

        annotations = getattr(function, "__annotations__", {})
        annotations.update({"return": None})
        self.schedule.__func__.__annotations__ = annotations
        self.schedule.__func__.__wrapped__ = function
