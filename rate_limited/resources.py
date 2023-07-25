from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from rate_limited.calls import Call

Unit = float


@dataclass
class UsageLog:
    timestamp: datetime
    amount: Unit


class Resource:
    def __init__(
        self,
        name: str,
        quota: Unit,
        time_window_seconds: float,
        arguments_usage_extractor: Optional[Callable[[Call], Unit]] = None,
        results_usage_extractor: Optional[Callable[[Any], Unit]] = None,
    ):
        """
        Defines a resource

        Args:
            name: name of the resource
            quota: maximum amount of the resource that can be used in the time window
            time_window_seconds: time window in seconds
            arguments_usage_extractor: function that extracts the amount of resource used from
                the arguments
            results_usage_extractor: function that extracts the amount of resource used from
                the results
        """
        self.name = name
        self.quota = quota
        self.time_window_seconds = time_window_seconds
        self._used = Unit(0)
        self.usage_log: deque = deque()

        self.arguments_usage_extractor = arguments_usage_extractor
        self.results_usage_extractor = results_usage_extractor
        # TODO: consider adding an optional estimator: taking arguments, returning max possible
        # usage from results

    def __repr__(self):
        return f"{self.name} - {self.get_usage()}/{self.quota} used"

    def add_usage(self, amount: Unit) -> None:
        # TODO: consider adding a time param - for better control over what timestamps are used
        self._used += amount
        self.usage_log.append(UsageLog(datetime.now(), amount))

    def get_usage(self) -> Unit:
        """
        Returns the amount used in the last time_window_seconds. Discards expired usage logs.
        """
        while self.usage_log and (
            (datetime.now() - self.usage_log[0].timestamp).seconds > self.time_window_seconds
        ):
            self._used -= self.usage_log.popleft().amount
        return self._used

    def get_remaining(self) -> Unit:
        return self.quota - self.get_usage()

    def is_available(self, amount) -> bool:
        return self.get_remaining() >= amount

    def get_next_expiration(self) -> datetime:
        """
        Returns the timestamp of the next expiration of a usage log. Returns current time
        if there are no usage logs.
        """
        if not self.usage_log:
            return datetime.now()
        return self.usage_log[0].timestamp + timedelta(seconds=self.time_window_seconds)
