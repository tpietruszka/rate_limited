import asyncio
import multiprocessing
import socketserver
from functools import partial
from time import sleep
from typing import Callable, List

import pytest
import requests
from aiohttp import ClientSession

from rate_limited.resources import Resource

from .dummy_server import start_app


@pytest.fixture()  # function scope - avoid polluting other tests
def running_dummy_server():
    """
    Spins up a dummy server, and returns its address.
    Cleans up after the test is done.
    """
    host = "localhost"

    # find a free port
    with socketserver.TCPServer((host, 0), socketserver.BaseRequestHandler) as s:
        free_port = s.server_address[1]

    start_app_bound = partial(start_app, host=host, port=free_port)
    p = multiprocessing.Process(target=start_app_bound)
    p.start()
    sleep(1)  # give it time to start

    address = f"http://{host}:{free_port}"
    yield address
    p.terminate()


@pytest.fixture
def test_executor_simple():
    """Just run the test scenario passed as argument"""

    def executor(test_scenario):
        return test_scenario()

    return executor


@pytest.fixture
def test_executor_asyncio():
    """
    Run the test scenario passed as argument in an asyncio event loop

    This is to mimic a Jupyter notebook, where the event loop is already running.
    """

    async def scenario_coro(test_scenario):
        return test_scenario()

    def executor(test_scenario):
        return asyncio.run(scenario_coro(test_scenario))

    return executor


def dummy_resources(
    num_requests: int = 3,
    num_points: int = 20,
    with_estimation: bool = True,
    time_window_seconds=5,
) -> List[Resource]:
    estimator = (lambda call: 2 * call.get_argument("how_many")) if with_estimation else None
    return [
        Resource(
            "requests",
            num_requests,
            time_window_seconds=time_window_seconds,
            arguments_usage_extractor=lambda _: 1,
        ),
        Resource(
            name="points",
            quota=num_points,
            time_window_seconds=time_window_seconds,
            results_usage_extractor=lambda _, result: result["used_points"],
            max_results_usage_estimator=estimator,
        ),
    ]


async def dummy_client_async(url: str, how_many: int, failure_proba: float = 0.0) -> dict:
    """Calls the dummy API - imitates an async API client"""
    # TODO: consider (and test for?) potential cases where a session is created
    # in the caller's code, within an existing event loop (!= Runner's event loop
    # started in its own thread)
    async with ClientSession() as session:
        async with session.get(
            f"{url}/calculate_things/{how_many}?failure_proba={failure_proba}"
        ) as result:
            result.raise_for_status()
            parsed = await result.json()
            return parsed


def dummy_client(url: str, how_many: int, failure_proba: float = 0.0) -> dict:
    """Calls the dummy API"""
    result = requests.get(f"{url}/calculate_things/{how_many}?failure_proba={failure_proba}")
    # this imitates the behavior of an API client, raising e.g. on a timeout error (or some
    # other kind of error)
    result.raise_for_status()
    parsed = result.json()
    return parsed


@pytest.fixture(params=("dummy_async", "dummy_sync"))
def test_client(request) -> Callable:
    """This gets instantiated twice - once for each client type - for each test that uses it"""
    name = request.param
    if name == "dummy_async":
        return dummy_client_async
    elif name == "dummy_sync":
        return dummy_client
    else:
        raise ValueError(f"Unknown client type: {name}")
