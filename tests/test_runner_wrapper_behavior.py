import re

from rate_limited.runner import Runner


def function_with_docstring(a: float, b: int = 1, **kwargs) -> int:
    """This is a docstring"""
    return 0


def function_without_docstring(a, b=1):
    pass


def test_update_schedule_as_wrapper():
    runner = Runner(function_with_docstring, [], 1)
    doc = runner.schedule.__doc__
    assert doc is not None
    assert "Schedule a call to function_with_docstring in" in doc
    # allowing for different formatting of the signature
    re.match(r"function_with_docstring\(a: float, b: int ?= ?1, \*\*kwargs\) -> int", doc)
    assert "This is a docstring" in doc

    annotations = runner.schedule.__annotations__
    assert annotations["return"] is None
    assert set(annotations.keys()) == {"a", "b", "return"}

    assert runner.schedule.__wrapped__ == function_with_docstring

    runner = Runner(function_without_docstring, [], 1)
    doc = runner.schedule.__doc__
    assert doc is not None
    assert "Schedule a call to function_without_docstring in" in doc
    re.match(r"function_without_docstring\(a, b ?= ?1\)", doc)
    assert "Docstring not found" in doc

    annotations = runner.schedule.__annotations__
    assert annotations["return"] is None
    assert set(annotations.keys()) == {"return"}

    assert runner.schedule.__wrapped__ == function_without_docstring
