import asyncio
from asyncio import Condition
from datetime import datetime
from logging import getLogger
from typing import Collection, Optional

from rate_limited.calls import Call
from rate_limited.resources import Resource, Unit


class ResourceManager:
    def __init__(self, resources: Collection[Resource]):
        self.resources = list(resources)
        self.condition: Optional[Condition] = None
        self.logger = getLogger("rate_limited.ResourceManager")
        self.num_waiting_for_resources = 0

    def initialize_in_event_loop(self):
        if self.condition is None:
            self.condition = Condition()
            return
        self.num_waiting_for_resources = 0

        current_loop = asyncio.get_running_loop()
        if self.condition._loop is not current_loop:  # type: ignore
            # new event loop -
            self.logger.debug("Detected event loop change - re-initializing condition")
            self.condition = Condition()

    def is_call_allowed(self, call: Call) -> bool:
        """
        Checks if the resources needed are below the quota - otherwise it will never be allowed
        """
        for resource in self.resources:
            needed = Unit(0)
            if resource.arguments_usage_extractor is not None:
                needed += resource.arguments_usage_extractor(call)
            if resource.max_results_usage_estimator is not None:
                needed += resource.max_results_usage_estimator(call)
            if needed > resource.quota:
                return False
        return True

    def register_call(self, call: Call):
        for resource in self.resources:
            if resource.arguments_usage_extractor:
                resource.add_usage(resource.arguments_usage_extractor(call))

    def pre_allocate(self, call: Call):
        for resource in self.resources:
            if resource.max_results_usage_estimator:
                resource.reserve_amount(resource.max_results_usage_estimator(call))

    def register_result(self, result):
        for resource in self.resources:
            if resource.results_usage_extractor:
                resource.add_usage(resource.results_usage_extractor(result))

    def remove_pre_allocation(self, call: Call):
        # Right now assuming that pre-allocation is only based on the call, this could change
        # to e.g. be also based on history of results
        for resource in self.resources:
            if resource.max_results_usage_estimator:
                resource.remove_reserved(resource.max_results_usage_estimator(call))

    def get_next_usage_expiration(self) -> datetime:
        return min(resource.get_next_expiration() for resource in self.resources)

    def _has_space_for_call(self, call: Call) -> bool:
        # important - we should NOT have any async code here!
        # (because we are inside a condition check)
        for resource in self.resources:
            needed = Unit(0)
            if resource.arguments_usage_extractor is not None:
                needed += resource.arguments_usage_extractor(call)
            if resource.max_results_usage_estimator is not None:
                needed += resource.max_results_usage_estimator(call)
            if not resource.is_available(needed):
                self.logger.debug(f"resource {resource.name} is not available: {resource}")
                return False
        self.logger.debug("all resources are available")
        return True

    async def wait_for_resources(self, call: Call):
        assert self.condition is not None
        async with self.condition:
            self.num_waiting_for_resources += 1
            await self.condition.wait_for(lambda: self._has_space_for_call(call))
            self.num_waiting_for_resources -= 1

    async def notify_waiting(self):
        assert self.condition is not None
        async with self.condition:
            # TODO: this is too eager, we could only wake a subset of workers
            # (exact solution non-trivial?, gains likely negligible)
            self.condition.notify_all()
