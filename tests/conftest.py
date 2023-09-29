import asyncio
import multiprocessing
import socketserver
from functools import partial
from time import sleep
from typing import List

import pytest

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
