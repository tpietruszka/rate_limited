"""
A dummy server that can be used for testing the rate limiter.
It calculates "things" - a string of length n, and returns it after a delay of n/10 seconds.

Calculating each "thing" uses 2 points.

There are 2 limits:
1. Number of requests per time window
2. Number of "points" per time window (each "thing" uses 2 points). Points could correspond to
   tokens in case of an LLM API - and the number of tokens used would only be known after the
   request is processed.
"""
import asyncio
import json
import random

from aiohttp import web

from rate_limited.resources import Resource

TIME_WINDOW_SECONDS = 5
REQUESTS_PER_TIME_WINDOW = 10
POINTS_PER_TIME_WINDOW = 100


def points_usage_from_n(n):
    return 2 * n


async def handle_request(request):
    """Handles an incoming GET request."""

    # might raise ValueError - not an issue for tests
    n = int(request.match_info.get("how_many"))
    points = points_usage_from_n(n)

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

    failure_proba = float(request.query.get("failure_proba", 0))
    if failure_proba and request.app["rng"].random() < failure_proba:
        return web.Response(
            body=json.dumps({"message": "Internal server error"}),
            content_type="application/json",
            status=500,
        )

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
    app["rng"] = random.Random(42)

    web.run_app(app, host=host, port=port)


if __name__ == "__main__":
    start_app()
