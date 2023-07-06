import asyncio
from typing import Callable, Collection, Generator

from rate_limited.calls import Call
from rate_limited.resources import Resource


class Runner:
    def __init__(self, function: Callable, resources: Collection[Resource], max_concurrent: int):
        self.function = function
        self.resources = resources  # TODO: how to pass tracking functions?
        self.queue: list[Call] = []
        self.max_concurrent = max_concurrent
        # TODO: add verification functions? (checking if response meets criteria, retrying otherwise)

    def schedule(self, *args, **kwargs):
        # TODO: use docstring from self.function?
        self.queue.append(Call(args, kwargs, 0))

    async def worker(self, calls: Generator[Call, None, None]):
        for call in calls:
            try:
                call.result = await self.function(*call.args, **call.kwargs)
            except Exception as e:
                call.exception = e

        # TODO: figure out returning results - if needed
        # TODO: retrying - with a limit; perhaps we have to go from generator to queue? (which will complicate result handling)
        # (or perhaps we can do a smarter generator?)
        # TODO: rate limiting

    async def run(self) -> list:
        # TODO: make sure calls are not scheduled while this is running?
        # (or support that case)
        calls_gen = (call for call in self.queue)
        workers = [self.worker(calls_gen) for _ in range(self.max_concurrent)]
        # TODO: handle notifications when resources are available again?
        await asyncio.gather(*workers)
        results = [call.result for call in self.queue]
        # TODO: how do we return/reports errors?
        self.queue = []
        # TODO: consider returning a generator, instead of waiting for all calls to finish?
        return results
