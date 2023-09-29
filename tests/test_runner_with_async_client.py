"""
This file tests cases where the API client is async (the callable passed to the Runner
is a coroutine function)

This is orthogonal to whether the runner is called from sync or async code, via `run_coro` or `run`

TODO: refactor test here and in `test_runner.py`, to have sync/async callables and sync/async
entrypoints as parameters (and run each scenario in all combinations)
"""
from aiohttp import ClientSession
from pytest import mark

from rate_limited.runner import Runner

from .conftest import dummy_resources

DEFAULT_MAX_CONCURRENT = 10


async def dummy_client(url: str, how_many: int, failure_proba: float = 0.0) -> dict:
    """Calls the dummy API - imitates an async API client"""
    session = ClientSession()
    async with session.get(
        f"{url}/calculate_things/{how_many}?failure_proba={failure_proba}"
    ) as result:
        result.raise_for_status()
        parsed = await result.json()
        return parsed


def test_runner_simple(running_dummy_server):
    runner = Runner(
        function=dummy_client,
        resources=dummy_resources(),
        max_concurrent=DEFAULT_MAX_CONCURRENT,
    )
    runner.schedule(running_dummy_server, 1)
    runner.schedule(running_dummy_server, 2)
    runner.schedule(running_dummy_server, 3)

    results, exceptions = runner.run()

    outputs = [result["output"] for result in results]
    assert outputs == ["x", "xx", "xxx"]

    # assumption here: resource use here is <= than the quota (all get executed immediately)
    points_used = [
        result["used_points"] + result["state_before_check"]["points"] for result in results
    ]
    assert max(points_used) == 2 * (1 + 2 + 3)

    assert exceptions == [[]] * 3


@mark.asyncio
async def test_runner_simple_from_coroutine(running_dummy_server):
    """Async client as above - but called from a coroutine"""
    runner = Runner(
        function=dummy_client,
        resources=dummy_resources(),
        max_concurrent=DEFAULT_MAX_CONCURRENT,
    )
    runner.schedule(running_dummy_server, 1)
    runner.schedule(running_dummy_server, 2)
    runner.schedule(running_dummy_server, 3)

    results, exceptions = runner.run()
    outputs = [result["output"] for result in results]
    assert outputs == ["x", "xx", "xxx"]

    points_used = [
        result["used_points"] + result["state_before_check"]["points"] for result in results
    ]
    assert max(points_used) == 2 * (1 + 2 + 3)

    assert exceptions == [[]] * 3
