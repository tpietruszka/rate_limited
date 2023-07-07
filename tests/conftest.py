import multiprocessing
import socketserver
from functools import partial
from time import sleep

import pytest
from dummy_server import start_app


@pytest.fixture()  # function scope - avoid polluting other tests
def running_dummy_server():
    """
    Spins up a dummy server, and returns its address.
    Cleans up after the test is done.
    """

    # find a free port
    with socketserver.TCPServer(("localhost", 0), None) as s:
        free_port = s.server_address[1]

    start_app_bound = partial(start_app, host="localhost", port=free_port)
    p = multiprocessing.Process(target=start_app_bound)
    p.start()
    sleep(1)  # give it time to start

    address = f"http://localhost:{free_port}"
    yield address
    p.terminate()
