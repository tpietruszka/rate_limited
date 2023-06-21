import asyncio
import json

from aiohttp import web

from rate_limited.resources import Resource

TIME_WINDOW_SECONDS = 5
REQUESTS_PER_TIME_WINDOW = 10
POINTS_PER_TIME_WINDOW = 100


async def handle_request(request):
    """Handles an incoming GET request."""

    # might raise ValueError - not an issue for tests
    n = int(request.match_info.get("how_many"))
    points = n * 2

    quotas_exceeded = []

    if not request.app["points_resource"].is_available(points):
        quotas_exceeded.append("Too many points used")
    if not request.app["requests_resource"].is_available(1):
        quotas_exceeded.append("Too many requests")

    if quotas_exceeded:
        return web.Response(
            body=json.dumps({"message": "".join(quotas_exceeded)}),
            content_type="application/json",
            status=429,
        )

    await asyncio.sleep(n / 100)

    data = {
        "output": "x" * n,
        "used_points": points,
    }
    response = web.Response(
        status=200,
        body=json.dumps(data),
        content_type="application/json",
    )

    # pessimistic approach - register usage long after the check, upon completion of the work
    request.app["requests_resource"].add_usage(1)
    request.app["points_resource"].add_usage(points)

    return response


def start_app():
    app = web.Application()
    app.add_routes(
        [
            web.get("/calculate_things/{how_many}", handle_request),
        ]
    )
    app["requests_resource"] = Resource(
        "requests", REQUESTS_PER_TIME_WINDOW, TIME_WINDOW_SECONDS
    )
    app["points_resource"] = Resource(
        "points", POINTS_PER_TIME_WINDOW, TIME_WINDOW_SECONDS
    )

    web.run_app(app)


if __name__ == "__main__":
    start_app()
