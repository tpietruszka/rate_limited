"""Intended to test the calls module - not performing actual calls to any API"""
from rate_limited.calls import Call


def sample_function(a, b, c=1, d=2, e=3):
    pass


def test_get_args():
    call = Call(sample_function, (1, 2), {"c": 3, "e": 5})
    # test args
    assert call.get_argument("a") == 1
    assert call.get_argument("b") == 2

    # test kwargs
    assert call.get_argument("c") == 3
    assert call.get_argument("e") == 5

    # test a default value
    assert call.get_argument("d") == 2

    # test a non-existent value
    assert call.get_argument("f") is None
