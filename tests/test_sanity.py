import requests


def test_dummy_server_sanity(running_dummy_server):
    """Tests a simple call to the dummy server - verifying the testing setup works"""
    # TODO: make host and port into constants
    response = requests.get("http://localhost:8080/calculate_things/1")
    assert response.status_code == 200
    assert response.json() == {"output": "x", "used_points": 2}
