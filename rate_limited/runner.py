import contextvars
import functools
import traceback
from asyncio import Condition, Queue, create_task, events, gather
from asyncio import sleep as asyncio_sleep
from asyncio import to_thread
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable, Collection

from rate_limited.calls import Call
from rate_limited.resources import Resource


class Runner:
    def __init__(
        self,
        function: Callable,
        resources: Collection[Resource],
        max_concurrent: int,
        max_retries: int = 0,
        min_wait_time: float = 1,
    ):
        self.function = function
        self.resource_manager = ResourceManager(resources)
        self.max_concurrent = max_concurrent
        self.executor = ThreadPoolExecutor(max_workers=max_concurrent)
        self.max_retries = max_retries
        self.min_wait_time = min_wait_time
        # TODO: add verification functions?
        # (checking if response meets criteria, retrying otherwise)

        # two views - one in order of scheduling, the other: tasks to execute, incl. retries
        self.scheduled_calls: list[Call] = []
        self.execution_queue = Queue()

    def schedule(self, *args, **kwargs):
        # TODO: use docstring from self.function?
        call = Call(args, kwargs, 0)
        self.scheduled_calls.append(call)
        self.execution_queue.put_nowait(call)

    async def worker(self):
        while True:
            # wait to get a task
            call = await self.execution_queue.get()
            # wait for resources to be available
            await self.resource_manager.wait_for_resources(call)

            # starting to execute - but first, register the usage
            self.resource_manager.register_call(call)
            try:
                # TODO: add a timeout mechanism?
                call.result = await to_thread(self.function, *call.args, **call.kwargs)
                # TODO: are there cases where we need to register result-based usage on error?
                # (one case: if we have user-defined verification functions)
                self.resource_manager.register_result(call.result)
            except Exception as e:
                # TODO: add logging?
                print(f"Exception: {e}")
                traceback.print_exception(e)
                call.exceptions.append(e)
                if call.num_retries < self.max_retries:
                    call.num_retries += 1
                    self.execution_queue.put_nowait(call)
            finally:
                self.execution_queue.task_done()

    async def to_thread_in_pool(self, func, /, *args, **kwargs):
        """Copy of asyncio.to_thread, but using a custom thread pool
        (and not requiring Python 3.9)

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
        return await loop.run_in_executor(self.executor, func_call)

    async def run(self) -> tuple[list, list]:
        """
        Runs the scheduled calls, returning a tuple of:
        - results (list, in order of scheduling) and
        - exceptions(list of lists, in order of scheduling)
        """
        worker_tasks = [create_task(self.worker()) for _ in range(self.max_concurrent)]

        # execution_queue.empty() will be true if all unfinished tasks have been taken by workers
        # (but some of them might still be waiting for resources)
        # TODO: consider a different mechanism, without relying on a private attribute
        # (maybe count the number of finished tasks externally?)
        while self.execution_queue._unfinished_tasks > 0:  # type: ignore
            now = datetime.now().timestamp()
            next_expiration = self.resource_manager.get_next_usage_expiration().timestamp()
            wait_time = (
                max(self.min_wait_time, next_expiration - now)
                if not self.execution_queue.empty()
                else self.min_wait_time
            )
            print(f"Queue size: {self.execution_queue.qsize()}, waiting for {wait_time} seconds")
            await asyncio_sleep(wait_time)
            async with self.resource_manager.condition:
                self.resource_manager.wake_workers()
        print("Queue is empty, waiting for workers to finish")
        await self.execution_queue.join()
        print("Workers finished, cancelling remaining tasks")
        for task in worker_tasks:
            task.cancel()
        print("Waiting for workers to finish")
        await gather(*worker_tasks, return_exceptions=True)
        print("Workers finished")
        results = [call.result for call in self.scheduled_calls]
        exception_lists = [call.exceptions for call in self.scheduled_calls]
        self.scheduled_calls = []
        # TODO: consider returning a generator, instead of waiting for all calls to finish?
        return results, exception_lists


class ResourceManager:
    def __init__(self, resources: Collection[Resource]):
        self.resources = list(resources)
        self.condition = Condition()

    def register_call(self, call: Call):
        for resource in self.resources:
            if resource.arguments_usage_extractor:
                resource.add_usage(resource.arguments_usage_extractor(call))

    def register_result(self, result):
        for resource in self.resources:
            if resource.results_usage_extractor:
                resource.add_usage(resource.results_usage_extractor(result))

    def get_next_usage_expiration(self) -> datetime:
        return min(resource.get_next_expiration() for resource in self.resources)

    def _has_space_for_call(self, call: Call) -> bool:
        # important - we should NOT have any async code here!
        # (because we are inside a condition check)
        for resource in self.resources:
            if resource.arguments_usage_extractor:
                needed = resource.arguments_usage_extractor(call)
            else:
                needed = 0
            if not resource.is_available(needed):
                print(f"resource {resource.name} is not available: {resource}")
                return False
        print("all resources are available")
        return True

    async def wait_for_resources(self, call: Call):
        async with self.condition:
            await self.condition.wait_for(lambda: self._has_space_for_call(call))

    def wake_workers(self):
        # TODO: this is too eager, we could only wake a subset of workers
        # (exact solution non-trivial?)
        self.condition.notify_all()
