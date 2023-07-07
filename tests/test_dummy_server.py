from concurrent.futures import ThreadPoolExecutor

import requests

from tests.dummy_server import (
    POINTS_PER_TIME_WINDOW,
    REQUESTS_PER_TIME_WINDOW,
    points_usage_from_n,
)


def test_dummy_server_sanity(running_dummy_server):
    """Tests a simple call to the dummy server - verifying the testing setup works"""
    # TODO: make host and port into constants
    response = requests.get(f"{running_dummy_server}/calculate_things/1")
    assert response.status_code == 200
    assert response.json() == {
        "output": "x",
        "used_points": 2,
        "state_before_check": {"points": 0, "requests": 0},
    }


def test_dummy_server_error(running_dummy_server):
    """Verify that the dummy server returns an error when requested"""
    response = requests.get(f"{running_dummy_server}/calculate_things/1?failure_proba=1")
    assert response.status_code == 500
    assert response.json() == {"message": "Internal server error"}


def test_dummy_server_rate_limit_requests(running_dummy_server):
    """Too many requests at once - should be rate limited"""
    n = REQUESTS_PER_TIME_WINDOW + 1
    with ThreadPoolExecutor(max_workers=n) as executor:
        futures = [
            executor.submit(requests.get, f"{running_dummy_server}/calculate_things/1")
            for _ in range(n)
        ]
        results = [future.result() for future in futures]
        assert sum(result.status_code == 200 for result in results) == REQUESTS_PER_TIME_WINDOW
        assert sum(result.status_code == 429 for result in results) == 1


def test_dummy_server_rate_limit_points(running_dummy_server):
    """Too many points at once - should be rate limited"""
    points_per_request = POINTS_PER_TIME_WINDOW

    # assuming points are a multiple of the request_param
    request_param = points_per_request // points_usage_from_n(1)

    n_requests = 2
    with ThreadPoolExecutor(max_workers=n_requests) as executor:
        futures = [
            executor.submit(
                requests.get, f"{running_dummy_server}/calculate_things/{request_param}"
            )
            for _ in range(n_requests)
        ]
        results = [future.result() for future in futures]
        assert sum(result.status_code == 200 for result in results) == 1
        assert sum(result.status_code == 429 for result in results) == 1
