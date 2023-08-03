import asyncio

import pytest
import requests

from rate_limited.resources import Resource
from rate_limited.runner import Runner


def dummy_client(url: str, how_many: int, failure_proba: float = 0.0) -> dict:
    """Calls the dummy API"""
    result = requests.get(f"{url}/calculate_things/{how_many}?failure_proba={failure_proba}")
    # this imitates the behavior of an API client, raising e.g. on a timeout error (or some
    # other kind of error)
    result.raise_for_status()
    parsed = result.json()
    return parsed


def dummy_resources(with_estimation: bool = True) -> list[Resource]:
    estimator = (lambda call: 2 * call.get_argument("how_many")) if with_estimation else None
    return [
        Resource("requests", 3, time_window_seconds=5, arguments_usage_extractor=lambda _: 1),
        Resource(
            name="points",
            quota=20,
            time_window_seconds=5,
            results_usage_extractor=lambda x: x["used_points"],
            max_results_usage_estimator=estimator,
        ),
    ]


def get_runner(resources: list[Resource]) -> Runner:
    """Runner instantiated to call the dummy API"""
    return Runner(
        dummy_client,
        resources=resources,
        max_concurrent=10,
        max_retries=5,
    )


def test_runner_simple(running_dummy_server):
    runner = get_runner(dummy_resources())
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


def test_runner_simple_from_coroutine(running_dummy_server):
    async def coro():
        # the content of coro() reflects how the the runner would be used in Jupyter,
        # (where everything happens within a coroutine)
        runner = get_runner(dummy_resources())
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


def test_runner_increasing_payloads(running_dummy_server):
    """
    Tuned so that at first the requests resource is exhausted, then the points resource.
    """
    runner = get_runner(dummy_resources())
    for i in range(1, 8):
        runner.schedule(running_dummy_server, i)

    results, exceptions = runner.run()

    outputs = [result["output"] for result in results]
    assert outputs == ["x" * i for i in range(1, 8)]


def test_runner_unreliable_server(running_dummy_server):
    """
    Testing results from an unreliable server - with a 50% chance of failure.
    """
    runner = get_runner(dummy_resources())

    for i in range(1, 8):
        runner.schedule(running_dummy_server, i, failure_proba=0.5)

    results, exceptions = runner.run()

    outputs = [result["output"] for result in results]
    assert outputs == ["x" * i for i in range(1, 8)]

    assert exceptions != [[]] * 10


def test_refuse_too_large_task(running_dummy_server):
    runner = get_runner(dummy_resources())
    with pytest.raises(ValueError, match="exceeds resource quota "):
        runner.schedule(running_dummy_server, 1000)
