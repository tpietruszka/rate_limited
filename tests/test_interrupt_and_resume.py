import asyncio
import os
import signal
import threading
import time

import pytest

from rate_limited.runner import Runner

from .conftest import dummy_client, dummy_resources


def wait_and_interrupt(wait_time_seconds: float):
    time.sleep(wait_time_seconds)
    os.kill(os.getpid(), signal.SIGINT)


@pytest.mark.xfail(reason="Python3.11 changed something about how signals are handled")
def test_interrupt_and_resume(running_dummy_server):
    """
    The use case we test here: in a context like Jupyter, we interrupt execution of
    the scheduled requests, inspect the partial results, then (optionally) resume execution
    to get the complete results.

    This is a weird use case, and testing handlers for SIGINT is not well supported.

    Further, in Python 3.11 (all else being equal) the test fails, because
    the KeyboardInterrupt is never raised. The functionality still works in Jupyter, though.
    TODO: figure out what changed in Python 3.11, and how to test this functionality.

    Detailed test scenario
    - schedule 4 requests, with resources to run 2 in each time window
    - run Runner.run()  (NB: this spawns a separate thread and a new event loop within it)
    - simulate KeyboardInterrupt (SIGINT) being sent (user clicks "interrupt" in Jupyter)
      with enough of a delay for first 2 requests to be completed
    - (we verify that partial results were returned)
    - run Runner.run() again
    - verify that the complete results were returned
    """

    num_requests_total = 4
    num_requests_per_window = 2
    time_window_seconds = 5

    request_param = 25
    request_points = 2 * request_param
    request_time = request_param / 10
    assert request_time < time_window_seconds
    points_quota = num_requests_per_window * request_points
    # we want the requests from the first window to be completed, but not the second
    wait_time = (request_time + time_window_seconds) / 2

    def scenario(running_dummy_server):
        runner = Runner(
            dummy_client,
            dummy_resources(
                num_requests=num_requests_per_window,
                num_points=points_quota,
                time_window_seconds=time_window_seconds,
            ),
        )

        for _ in range(num_requests_total):
            runner.schedule(running_dummy_server, request_param)
        results, exceptions = runner.run()

        outputs = [result["output"] for result in results if result is not None]
        assert outputs == ["x" * request_param] * num_requests_per_window
        assert exceptions == [[]] * num_requests_total

        results, exceptions = runner.run()
        outputs = [result["output"] for result in results]
        assert outputs == ["x" * request_param] * num_requests_total
        assert exceptions == [[]] * num_requests_total

    async def scenario_coro(running_dummy_server):
        return scenario(running_dummy_server)

    threading.Thread(target=wait_and_interrupt, args=(wait_time,)).start()
    asyncio.run(scenario_coro(running_dummy_server))
