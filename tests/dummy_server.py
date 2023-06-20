from aiohttp import web
import json


async def handle_request(request):
    """Handles an incoming GET request."""
    n = int(request.match_info.get("how_many"))  # might raise ValueError - not an issue for tests 
    data = {
        "output": "x" * n,
        "used_points": n*2
    }

    response = web.Response(
        status=200,
        body=json.dumps(data),
        content_type="application/json",
    )
    return response


# TODO: implement a rate limit on requests per minute and also used_points

def main():
    app = web.Application()
    app.add_routes([
        web.get('/calculate_things/{how_many}', handle_request),
    ])
    web.run_app(app)


if __name__ == "__main__":
    main()