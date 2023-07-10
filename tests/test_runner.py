import asyncio

import requests
from pytest import fixture

from rate_limited.resources import Resource
from rate_limited.runner import Runner


# TODO: move?
@fixture
def dummy_resources():
    return [
        Resource("requests", 5, time_window_seconds=5, arguments_usage_extractor=lambda _: 1),
        Resource(
            "points", 10, time_window_seconds=10, results_usage_extractor=lambda x: x["used_points"]
        ),
    ]


def call_dummy_api(url, how_many, failure_proba=0):
    """Calls the dummy API"""
    result = requests.get(f"{url}/calculate_things/{how_many}?failure_proba={failure_proba}").json()
    print(f"Got result: {result}")
    return result


# TODO: add an async API, mark both as parametrrized


def test_runner_simple(running_dummy_server, dummy_resources):
    runner = Runner(
        call_dummy_api,
        resources=dummy_resources,
        max_concurrent=10,
        max_retries=5,
    )
    runner.schedule(running_dummy_server, 1)
    runner.schedule(running_dummy_server, 2)
    runner.schedule(running_dummy_server, 3)

    results, exceptions = asyncio.run(runner.run())

    # TODO: can the way of running the runner be improved?

    outputs = [result["output"] for result in results]
    assert outputs == ["x", "xx", "xxx"]

    points_used = [
        result["used_points"] + result["state_before_check"]["points"] for result in results
    ]
    assert max(points_used) == 2 * (1 + 2 + 3)

    assert exceptions == [[]] * 3


def test_runner_simple_from_coroutine(running_dummy_server, dummy_resources):
    async def coro():
        # the content of coro() reflects how the the runner would be used in Jupyter,
        # (where everything happens within a coroutine)
        runner = Runner(
            call_dummy_api,
            resources=dummy_resources,
            max_concurrent=10,
            max_retries=5,
        )
        runner.schedule(running_dummy_server, 1)
        runner.schedule(running_dummy_server, 2)
        runner.schedule(running_dummy_server, 3)

        results, exceptions = await runner.run()
        outputs = [result["output"] for result in results]
        assert outputs == ["x", "xx", "xxx"]

        points_used = [
            result["used_points"] + result["state_before_check"]["points"] for result in results
        ]
        assert max(points_used) == 2 * (1 + 2 + 3)

        assert exceptions == [[]] * 3

    asyncio.run(coro())
