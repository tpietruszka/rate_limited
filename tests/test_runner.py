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


def dummy_resources(
    num_requests: int = 3, num_points: int = 20, with_estimation: bool = True
) -> list[Resource]:
    estimator = (lambda call: 2 * call.get_argument("how_many")) if with_estimation else None
    return [
        Resource(
            "requests", num_requests, time_window_seconds=5, arguments_usage_extractor=lambda _: 1
        ),
        Resource(
            name="points",
            quota=num_points,
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


def test_runner_without_estimation(running_dummy_server):
    """
    Runner with estimation - temporarily exceeds the points quota.

    The dummy server only registers usage when the results are returned,
    which allows more tasks to start in parallel than the points quota allows.

    This is to be contrasted with the similar test below, which uses the same resources, but
    with estimation enabled.
    """
    num_requests = 10
    # setting the number of points to be equal to the number of requests,
    # so points quota actually only lets through half of the requests at a time
    runner = get_runner(
        dummy_resources(num_requests=num_requests, num_points=num_requests, with_estimation=False)
    )

    for _ in range(num_requests):
        runner.schedule(running_dummy_server, 1)

    results, exceptions = runner.run()

    outputs = [result["output"] for result in results]
    assert outputs == ["x"] * num_requests
    assert exceptions == [[]] * num_requests

    # check that the points quota was not exceeded
    points_used = [
        result["used_points"] + result["state_before_check"]["points"] for result in results
    ]
    assert max(points_used) == num_requests * 2


def test_runner_with_estimation(running_dummy_server):
    """
    Runner with estimation - does not exceed the points quota.

    The dummy server only registers usage when the results are returned, but others would kill
    requests mid-way. We wan't to make sure this won't happen in this scenario
    """
    num_requests = 10
    # setting the number of points to be equal to the number of requests,
    # so points quota actually only lets through half of the requests at a time
    runner = get_runner(
        dummy_resources(num_requests=num_requests, num_points=num_requests, with_estimation=True)
    )

    for _ in range(num_requests):
        runner.schedule(running_dummy_server, 1)

    results, exceptions = runner.run()

    outputs = [result["output"] for result in results]
    assert outputs == ["x"] * num_requests
    assert exceptions == [[]] * num_requests

    # check that the points quota was not exceeded
    points_used = [
        result["used_points"] + result["state_before_check"]["points"] for result in results
    ]
    assert max(points_used) <= num_requests
