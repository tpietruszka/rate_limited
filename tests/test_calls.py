"""Intended to test the calls module - not performing actual calls to any API"""
from rate_limited.calls import Call


def sample_function(a, b, c=1, d=2, e=3):
    pass


def sample_function_with_kwargs(a, b, c=1, d=2, **kwargs):
    pass


def test_get_argument_simple():
    call = Call(sample_function, (1, 2), {"c": 3, "e": 5})
    # positional arguments
    assert call.get_argument("a") == 1
    assert call.get_argument("b") == 2

    # keyword arguments
    assert call.get_argument("c") == 3
    assert call.get_argument("e") == 5

    # a default value
    assert call.get_argument("d") == 2

    # a non-existent value
    assert call.get_argument("f") is None


def test_arguments_with_kwargs():
    call = Call(sample_function_with_kwargs, (1, 2), {"c": 3, "e": 5})
    # positional arguments
    assert call.get_argument("a") == 1
    assert call.get_argument("b") == 2

    # a keyword argument
    assert call.get_argument("c") == 3

    # an arbitrary keyword argument
    assert call.get_argument("e") == 5

    # a default value
    assert call.get_argument("d") == 2

    # a non-existent value
    assert call.get_argument("f") is None
