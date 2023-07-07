import multiprocessing
from time import sleep

import pytest
from dummy_server import start_app


@pytest.fixture()  # function scope - avoid polluting other tests
def running_dummy_server():
    p = multiprocessing.Process(target=start_app)
    p.start()
    sleep(1)  # give it time to start
    yield
    p.terminate()
