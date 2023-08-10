from rate_limited.resources import Resource


def get_requests_per_minute(quota: int) -> Resource:
    return Resource(
        name="requests_per_minute",
        quota=quota,
        time_window_seconds=60,
        arguments_usage_extractor=lambda _: 1,
    )
