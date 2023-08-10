from dataclasses import dataclass, field
from functools import cached_property
from inspect import signature
from typing import Any, Callable, List


@dataclass
class Call:
    function: Callable
    args: tuple
    kwargs: dict
    num_retries: int = 0
    result: Any = None
    exceptions: List[Exception] = field(default_factory=list)

    @cached_property
    def all_arguments_dict(self) -> dict:
        all_args_dict = signature(self.function).bind(*self.args, **self.kwargs).arguments
        kwargs = all_args_dict.pop("kwargs", {})
        return {**all_args_dict, **kwargs}

    @cached_property
    def default_params(self) -> dict:
        return {
            name: param.default
            for name, param in signature(self.function).parameters.items()
            if param.default is not param.empty
        }

    def get_argument(self, name: str) -> Any:
        """
        Returns the value of the argument with the given name - whether it was passed positionally,
        as a keyword argument, or as a default value.
        """
        return self.all_arguments_dict.get(name) or self.default_params.get(name)
