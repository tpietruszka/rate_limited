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
        max_results_usage_estimator: Optional[Callable[[Call], Unit]] = None,
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
            max_results_usage_estimator: function that extracts an upper bound on the amount of
                resource that might be used when results are returned, based on the arguments
                (this is used to pre-allocate usage, pre-allocation is then replaced with the
                actual usage when the results are returned). Only used in combination with
                results_usage_extractor.
        """
        self.name = name
        self.quota = quota
        self.time_window_seconds = time_window_seconds
        self._used = Unit(0)
        self.usage_log: deque = deque()
        self._reserved = Unit(0)

        self.arguments_usage_extractor = arguments_usage_extractor
        self.results_usage_extractor = results_usage_extractor
        self.max_results_usage_estimator = max_results_usage_estimator  # TODO: consider renaming

        if self.max_results_usage_estimator and not self.results_usage_extractor:
            raise ValueError(
                "max_results_usage_estimator can only be used when results_usage_extractor is "
                "also provided"
            )

    def __repr__(self):
        return (
            f"Resource: {self.name} - available: {self.get_amount_available()}/{self.quota}"
            f" (used: {self._used}, reserved: {self._reserved})"
        )

    def add_usage(self, amount: Unit) -> None:
        self._used += amount
        self.usage_log.append(UsageLog(datetime.now(), amount))

    def reserve_amount(self, amount: Unit) -> None:
        self._reserved += amount

    def remove_reserved(self, amount: Unit) -> None:
        self._reserved -= amount

    def _discard_old_logs(self):
        while self.usage_log and (
            (datetime.now() - self.usage_log[0].timestamp).seconds > self.time_window_seconds
        ):
            self._used -= self.usage_log.popleft().amount

    def get_amount_used(self) -> Unit:
        """
        Returns the amount used in the last time_window_seconds - ignoring reserved amounts.
        """
        self._discard_old_logs()
        return self._used

    def get_amount_available(self) -> Unit:
        """
        Returns the amount available - taking into account reserved amounts.
        """
        return self.quota - self.get_amount_used() - self._reserved

    def is_available(self, amount) -> bool:
        """
        Returns True if there is enough remaining quota to use the given amount.
        """
        return self.get_amount_available() >= amount

    def get_next_expiration(self) -> datetime:
        """
        Returns the timestamp of the next expiration of a usage log. Returns current time
        if there are no usage logs.
        """
        self._discard_old_logs()
        if not self.usage_log:
            return datetime.now()
        return self.usage_log[0].timestamp + timedelta(seconds=self.time_window_seconds)
