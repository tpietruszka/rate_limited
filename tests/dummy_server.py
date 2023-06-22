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

    points_resource = request.app["points_resource"]
    requests_resource = request.app["requests_resource"]

    allowed = False
    state_before_check = str((points_resource, requests_resource))
    if points_resource.is_available(points) and requests_resource.is_available(1):
        allowed = True
        requests_resource.add_usage(1)
        points_resource.add_usage(points)

    if not allowed:
        return web.Response(
            body=json.dumps({"message": "Some rate limits exceeded: " + state_before_check}),
            content_type="application/json",
            status=429,
        )

    await asyncio.sleep(n / 10)

    data = {
        "output": "x" * n,
        "used_points": points,
    }
    response = web.Response(
        status=200,
        body=json.dumps(data),
        content_type="application/json",
    )
    return response


def start_app(host="localhost", port=8080):
    app = web.Application()
    app.add_routes(
        [
            web.get("/calculate_things/{how_many}", handle_request),
        ]
    )
    app["requests_resource"] = Resource("requests", REQUESTS_PER_TIME_WINDOW, TIME_WINDOW_SECONDS)
    app["points_resource"] = Resource("points", POINTS_PER_TIME_WINDOW, TIME_WINDOW_SECONDS)

    web.run_app(app, host=host, port=port)


if __name__ == "__main__":
    start_app()
