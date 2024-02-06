import random
from functools import partial

import pytest
import requests

from rate_limited.exceptions import ValidationError
from rate_limited.runner import Runner

from .conftest import dummy_client, dummy_client_async, dummy_resources

DEFAULT_MAX_CONCURRENT = 10


def test_runner_simple(running_dummy_server):
    """
    Simplest case - run a few tasks that get executed immediately.

    Largely illustrative purpose
    """
    runner = Runner(dummy_client, dummy_resources(), max_concurrent=DEFAULT_MAX_CONCURRENT)
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


@pytest.mark.asyncio
async def test_runner_simple_from_coroutine(running_dummy_server):
    """
    Reflects how the the runner would be used in Jupyter,
    where everything happens in the context of an event loop.
    """
    runner = Runner(dummy_client, dummy_resources(), max_concurrent=DEFAULT_MAX_CONCURRENT)
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


def test_async_runner_simple(running_dummy_server):
    """
    Simplest use case where the API client is async (the callable passed to the Runner
    is a coroutine function)
    """
    runner = Runner(
        function=dummy_client_async,
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


@pytest.mark.asyncio
async def test_async_runner_simple_from_coroutine(running_dummy_server):
    runner = Runner(
        function=dummy_client_async,
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


def test_runner_increasing_payloads(running_dummy_server, test_client):
    """
    Tuned so that at first the requests resource is exhausted, then the points resource.
    """
    runner = Runner(test_client, dummy_resources(), max_concurrent=DEFAULT_MAX_CONCURRENT)
    for i in range(1, 8):
        runner.schedule(running_dummy_server, i)

    results, exceptions = runner.run()

    outputs = [result["output"] for result in results]
    assert outputs == ["x" * i for i in range(1, 8)]


def test_runner_unreliable_server(running_dummy_server, test_client):
    """
    Testing results from an unreliable server - with a 50% chance of failure.
    """
    runner = Runner(
        test_client, dummy_resources(), max_concurrent=DEFAULT_MAX_CONCURRENT, max_retries=10
    )

    for i in range(1, 8):
        runner.schedule(running_dummy_server, i, failure_proba=0.5)

    results, exceptions = runner.run()

    outputs = [result["output"] for result in results]
    assert outputs == ["x" * i for i in range(1, 8)]

    assert exceptions != [[]] * 10


def test_refuse_too_large_task(running_dummy_server, test_client):
    runner = Runner(test_client, dummy_resources(), max_concurrent=DEFAULT_MAX_CONCURRENT)
    with pytest.raises(ValueError, match="exceeds resource quota "):
        runner.schedule(running_dummy_server, 1000)


def test_runner_without_estimation(running_dummy_server, test_client):
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
    runner = Runner(
        test_client,
        dummy_resources(num_requests=num_requests, num_points=num_requests, with_estimation=False),
        max_concurrent=DEFAULT_MAX_CONCURRENT,
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


def test_runner_with_estimation(running_dummy_server, test_client):
    """
    Runner with estimation - does not exceed the points quota.

    The dummy server only registers usage when the results are returned, but others would kill
    requests mid-way. We wan't to make sure this won't happen in this scenario
    """
    num_requests = 10
    # setting the number of points to be equal to the number of requests,
    # so points quota actually only lets through half of the requests at a time
    runner = Runner(
        test_client,
        dummy_resources(num_requests=num_requests, num_points=num_requests, with_estimation=True),
        max_concurrent=DEFAULT_MAX_CONCURRENT,
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


@pytest.mark.parametrize("test_executor_name", ["test_executor_simple", "test_executor_asyncio"])
@pytest.mark.timeout(15, method="thread")  # a likely failure mode here is a deadlock
def test_two_runs_to_completion(running_dummy_server, request, test_executor_name, test_client):
    """
    After a run(), we support schedule()-ing more tasks and running them.

    Running twice - from normal sync code, and from a context with an event loop.
    """
    test_executor = request.getfixturevalue(test_executor_name)

    def scenario():
        num_requests = 4
        runner = Runner(
            test_client,
            dummy_resources(num_requests=2, num_points=100, time_window_seconds=2),
            max_concurrent=DEFAULT_MAX_CONCURRENT,
        )

        for _ in range(num_requests):
            runner.schedule(running_dummy_server, 1)

        results, exceptions = runner.run()
        outputs = [result["output"] for result in results]
        assert outputs == ["x"] * num_requests
        assert exceptions == [[]] * num_requests

        for _ in range(num_requests):
            runner.schedule(running_dummy_server, 2)

        results, exceptions = runner.run()
        outputs = [result["output"] for result in results]
        assert outputs == ["xx"] * num_requests
        assert exceptions == [[]] * num_requests

    test_executor(scenario)


def test_result_validation(running_dummy_server):
    """
    Check that the results are validated using the validation function and retried if necessary.
    """
    rng = random.Random(42)

    # TODO: consider also testing a random async client
    def random_client(url: str, how_many=2, failure_proba: float = 0.2) -> dict:
        """Request between 1 and `how_many` calculations from the server, with a `failure_proba`"""
        how_many = rng.randint(1, how_many)
        result = requests.get(f"{url}/calculate_things/{how_many}?failure_proba={failure_proba}")
        # this imitates the behavior of an API client, raising e.g. on a timeout error (or some
        # other kind of error)
        result.raise_for_status()
        parsed = result.json()
        return parsed

    def validate(result: dict) -> bool:
        return result["output"].count("x") == 2

    runner = Runner(
        random_client,
        resources=dummy_resources(num_requests=5),
        validators=validate,
        max_concurrent=5,
        max_retries=10,
    )
    num_requests = 5
    for _ in range(num_requests):
        runner.schedule(running_dummy_server)

    results, exceptions = runner.run()
    outputs = [result["output"] for result in results]
    assert outputs == ["xx"] * num_requests

    exceptions_flat = [
        e
        for sublist in exceptions
        for e in sublist
    ]
    assert any(isinstance(e, ValidationError) for e in exceptions_flat)


def test_with_partial_bound_kwarg(running_dummy_server, test_client):
    NUM_REQUESTS = 3
    client_bound_kwarg = partial(test_client, failure_proba=0.05)
    runner = Runner(client_bound_kwarg, dummy_resources())
    for _ in range(1, NUM_REQUESTS + 1):
        runner.schedule(running_dummy_server, 1)
    results, _ = runner.run()
    outputs = [result["output"] for result in results]
    assert outputs == ["x"] * NUM_REQUESTS


def test_with_partial_bound_positional_arg(running_dummy_server, test_client):
    NUM_REQUESTS = 3
    client_bound = partial(test_client, running_dummy_server)
    runner = Runner(client_bound, dummy_resources())
    for _ in range(1, NUM_REQUESTS + 1):
        runner.schedule(1)
    results, _ = runner.run()
    outputs = [result["output"] for result in results]
    assert outputs == ["x"] * NUM_REQUESTS


def test_with_partial_bound_mixed_args(running_dummy_server, test_client):
    NUM_REQUESTS = 3
    # binding first positional arg using kwargs syntax and one of the kwargs
    client_bound = partial(test_client, url=running_dummy_server, failure_proba=0.05)
    runner = Runner(client_bound, dummy_resources())
    # note: how_many has to be passed as a kwarg, because a preceding positional arg is bound
    # using kwargs syntax
    for _ in range(1, NUM_REQUESTS + 1):
        runner.schedule(how_many=1)
    results, _ = runner.run()
    outputs = [result["output"] for result in results]
    assert outputs == ["x"] * NUM_REQUESTS


def test_with_lambda(running_dummy_server):
    """
    note: only supporting sync clients wrapped in lambdas
    """
    NUM_REQUESTS = 3
    runner = Runner(
        lambda how_many: dummy_client(running_dummy_server, how_many), dummy_resources()
    )
    for _ in range(1, NUM_REQUESTS + 1):
        runner.schedule(1)
    results, _ = runner.run()
    outputs = [result["output"] for result in results]
    assert outputs == ["x"] * NUM_REQUESTS
