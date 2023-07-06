from dataclasses import dataclass, field
from typing import Any


@dataclass
class Call:
    args: tuple
    kwargs: dict
    num_retries: int = 0
    result: Any = None
    exceptions: list[Exception] = field(default_factory=list)
