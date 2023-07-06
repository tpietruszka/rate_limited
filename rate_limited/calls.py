from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Call:
    args: tuple
    kwargs: dict
    num_retries: int
    result: Any = None
    exception: Optional[Exception] = None