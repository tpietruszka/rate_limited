import asyncio

import pytest
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
            name="points",
            quota=10,
            time_window_seconds=10,
            results_usage_extractor=lambda x: x["used_points"],
            max_results_usage_estimator=lambda call: 2 * call.get_argument("how_many"),
        ),
    ]


def call_dummy_api(url, how_many, failure_proba=0):
    """Calls the dummy API"""
    result = requests.get(f"{url}/calculate_things/{how_many}?failure_proba={failure_proba}")
    # this imitates the behavior of an API client, raising e.g. on a timeout error (or some
    # other kind of error)
    result.raise_for_status()

    parsed = result.json()
    return parsed


# TODO: add an async API, run tests with both via "parametrized"


@fixture
def runner(dummy_resources):
    """Runner instantiated to call the dummy API"""
    return Runner(
        call_dummy_api,
        resources=dummy_resources,
        max_concurrent=10,
        max_retries=5,
    )


def test_runner_simple(running_dummy_server, runner):
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


def test_runner_simple_from_coroutine(running_dummy_server, runner):
    async def coro():
        # the content of coro() reflects how the the runner would be used in Jupyter,
        # (where everything happens within a coroutine)
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


def test_runner_increasing_payloads(running_dummy_server, runner):
    """
    Tuned so that at first the requests resource is exhausted, then the points resource.
    """
    for i in range(1, 11):
        runner.schedule(running_dummy_server, i)

    results, exceptions = runner.run()

    outputs = [result["output"] for result in results]
    assert outputs == ["x" * i for i in range(1, 11)]


def test_runner_unreliable_server(running_dummy_server, runner):
    """
    Testing results from an unreliable server - with a 50% chance of failure.
    """
    for i in range(1, 11):
        runner.schedule(running_dummy_server, i, failure_proba=0.5)

    results, exceptions = runner.run()

    outputs = [result["output"] for result in results]
    assert outputs == ["x" * i for i in range(1, 11)]

    assert exceptions != [[]] * 10


def test_refuse_too_large_task(runner, running_dummy_server):
    with pytest.raises(ValueError, match="exceeds resource quota "):
        runner.schedule(running_dummy_server, 1000)
