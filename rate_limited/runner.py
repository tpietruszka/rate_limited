from asyncio import Queue, create_task, gather
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
    ):
        self.function = function
        self.resources = resources  # TODO: how to pass tracking functions?
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        # TODO: add verification functions? (checking if response meets criteria, retrying otherwise)

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
            call = await self.execution_queue.get()
            try:
                call.result = await self.function(*call.args, **call.kwargs)
            except Exception as e:
                # TODO: add logging?
                call.exceptions.append(e)
                if call.num_retries < self.max_retries:
                    call.num_retries += 1
                    self.execution_queue.put_nowait(call)
            finally:
                self.execution_queue.task_done()

        # TODO: figure out returning results - if needed
        # TODO: retrying - with a limit; perhaps we have to go from generator to queue? (which will complicate result handling)
        # (or perhaps we can do a smarter generator?)
        # TODO: rate limiting

    async def run(self) -> list:
        # TODO: make sure calls are not scheduled while this is running?
        # (or support that case)
        worker_tasks = [create_task(self.worker()) for _ in range(self.max_concurrent)]
        # TODO: handle notifications when resources are available again?
        await self.execution_queue.join()
        for task in worker_tasks:
            task.cancel()
        await gather(*worker_tasks, return_exceptions=True)
        results = [call.result for call in self.scheduled_calls]
        # TODO: how do we return/reports errors?
        self.scheduled_calls = []
        # TODO: consider returning a generator, instead of waiting for all calls to finish?
        return results
