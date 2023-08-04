from dataclasses import dataclass, field
from functools import cached_property
from inspect import signature
from typing import Any, Callable


@dataclass
class Call:
    function: Callable
    args: tuple
    kwargs: dict
    num_retries: int = 0
    result: Any = None
    exceptions: list[Exception] = field(default_factory=list)

    @cached_property
    def all_arguments_dict(self) -> dict:
        all_args_dict = signature(self.function).bind(*self.args, **self.kwargs).arguments
        return all_args_dict

    def get_argument(self, name: str) -> Any:
        """
        Returns the value of the argument with the given name - whether it was passed positionally
        or as a keyword argument.
        """
        return self.all_arguments_dict.get(name)
