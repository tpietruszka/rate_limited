from collections import deque
from dataclasses import dataclass
from datetime import datetime


@dataclass
class UsageLog:
    timestamp: datetime
    amount: int


class Resource:
    def __init__(self, name: str, quota: float, time_window_seconds: float):
        self.name = name
        self.quota = quota
        self.time_window_seconds = time_window_seconds
        self._used = 0
        self.usage_log = deque()

    def __repr__(self):
        return f"{self.name} - {self.get_usage()}/{self.quota} used"

    def add_usage(self, amount):
        # TODO: consider adding a time param - for better control over what timestamps are used
        self._used += amount
        self.usage_log.append(UsageLog(datetime.now(), amount))

    def get_usage(self):
        while self.usage_log and (
            (datetime.now() - self.usage_log[0].timestamp).seconds > self.time_window_seconds
        ):
            self._used -= self.usage_log.popleft().amount
        return self._used

    def get_remaining(self):
        return self.quota - self.get_usage()

    def is_available(self, amount):
        return self.get_remaining() >= amount
