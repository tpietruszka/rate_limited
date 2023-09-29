# rate_limited
[![PyPI version](https://badge.fury.io/py/rate-limited.svg)](https://badge.fury.io/py/rate-limited)
![Python versions](https://img.shields.io/badge/python-3.8+-blue.svg)
[![Lint and test](https://github.com/tpietruszka/rate_limited/actions/workflows/lint-and-test.yml/badge.svg?branch=main)](https://github.com/tpietruszka/rate_limited/actions/workflows/lint-and-test.yml?query=branch:main)
[![Publish to PyPI](https://github.com/tpietruszka/rate_limited/actions/workflows/pypi-publish.yml/badge.svg)](https://github.com/tpietruszka/rate_limited/actions/workflows/pypi-publish.yml)

A lightweight package meant to enable **efficient parallel use of slow, rate-limited APIs** - like
those of Large Language Models (LLMs).

## Features
- parallel execution - be as quick as possible within the rate limit you have
- retry failed requests
- validate the response against your criteria and retry if not valid (for non-deterministic APIs)
- if interrupted (`KeyboardInterrupt`) e.g. in a notebook:
   - returns partial results
  - if ran again, continues from where it left off - and returns full results
- rate limits of some popular APIs already described - custom ones easy to add
- no dependencies (will use tqdm progress bars if installed)


## Assumptions:
- the client:
  - handles timeouts (requests will not hang forever)
  - raises an exception if the request fails (or the server returns an error / an "invalid" response)
  - can be any type of a callable - function, method, coroutine function, partial, etc
- requests are independent from each other, can be retried if failed
- we want a standard, simple interface for the user - working the same way in a script and in a
  notebook (+ most data scientists do not want to deal with asyncio). Therefore, `Runner.run()` is
  a blocking call, with the same behavior regardless of the context.
- async use is also supported - via `run_coro()` - but it will not support `KeyboardInterrupt`
  handling.

## Installation
```shell
pip install rate_limited
```

## Usage
In short:
- wrap your function with a `Runner()`, describing the rate limits you have
- call `Runner.schedule()` to schedule a request - with the same arguments as you would call the
  original function
- call `Runner.run()` to run the scheduled requests, get the results and any exceptions raised
  (**results are returned in the order of scheduling**)

### Creating a Runner
The following arguments are required:
- `function` - the callable of the API client
- `resources` - a list of `Resource` objects, describing the rate limits you have (see examples below)

Important optional arguments:
- `max_retries` - the maximum number of retries for a single request (default: 5)
- `max_concurrent` - the maximum number of requests to be executed in parallel (default: 64)
- `validation_function` - a function that validates the response and returns `True` if it is valid
  (e.g. conforms to the schema you expect). If not valid, the request will be retried.

### OpenAI example
```python
import openai
from rate_limited.runner import Runner
from rate_limited.apis.openai import chat

openai.api_key = "YOUR_API_KEY"
model = "gpt-3.5-turbo"

# describe your rate limits - values based on https://platform.openai.com/account/rate-limits
resources = chat.openai_chat_resources(
    requests_per_minute=3_500,
    tokens_per_minute=90_000,
    model_max_len=4096,  # property of the model version in use - max sequence length
)
runner = Runner(openai.ChatCompletion.create, resources)

topics = ["honey badgers", "llamas", "pandas"]
for topic in topics:
    messages = [{"role": "user", "content": f"Please write a poem about {topic}"}]
    # call runner.schedule exactly like you would call openai.ChatCompletion.create
    runner.schedule(model=model, messages=messages, max_tokens=256, request_timeout=60)

results, exceptions = runner.run()
```

### Validating the response
We can provide custom validation logic to the Runner - to retry the request if the response
does not meet our criteria - for example, if it does not conform to the schema we expect. This
assumes that the API is non-deterministic.

Example above continued:
```python
def character_number_is_even(response):
    poem = response["choices"][0]["message"]["content"]
    return len([ch for ch in poem if ch.isalpha()]) % 2 == 0

validating_runner = Runner(
    openai.ChatCompletion.create,
    resources,
    validation_function=character_number_is_even,
)
for topic in topics:
    messages = [{"role": "user", "content": f"Please write a short poem about {topic}, containing an even number of letters"}]
    validating_runner.schedule(model=model, messages=messages, max_tokens=256, request_timeout=60)
results, exceptions = validating_runner.run()
```

### Custom server with a "requests per minute" limit
proceed as above - replace `openai.ChatCompletion.create` with your own function, and
describe resources as follows:
```python
from rate_limited.resources import Resource
resources = [
  Resource(
            "requests_per_minute",
            quota=100,
            time_window_seconds=60,
            arguments_usage_extractor=lambda _: 1,
        ),
]
```

### More complex resource descriptions

Overall, the core of an API description is a list of `Resource` objects, each describing a single
resource and its limit - e.g. "requests per minute", "tokens per minute", "images per hour", etc.

Each resource has:
- a name (just for logging/debugging)
- a quota (e.g. 100)
- a time window (e.g. 60 seconds)
- functions that extract the "billing" information:
  - `arguments_usage_extractor`
  - `results_usage_extractor`
  - `max_results_usage_estimator`

Two distinct "billing" models are supported:
- Before the call - we register usage before making the call, based on the arguments of the call.

  In these cases, just `arguments_usage_extractor` is needed.
- After the call - we register usage after making the call, based on the results of the call,
  and possibly the arguments (if needed for some complex cases).

  To avoid sending a flood or requests before the first ones complete (and we register any usage)
  we need to estimate the maximum usage of each call, based on its arguments. We
  "pre-allocate" this usage, then register the actual usage after the call completes.

  In these cases, `results_usage_extractor` and `max_results_usage_estimator` are needed.

Both approaches can be used in the same Resource description if needed.

Note: it is assumed that resource usage "expires" fully after the time window elapses, without a
"gradual" decline. Some APIs (OpenAI) might use the "gradual" approach, and differ in other details,
but this approach seems sufficient to get "close enough" to the actual rate limits, without running
into them.

### Limiting the number of concurrent requests

The `max_concurrent` argument of `Runner` controls the number of concurrent requests.

### More advanced usage

See [apis.openai.chat](./rate_limited/apis/openai/chat.py) for an example of a more complex API
description with multiple resources.

## Implementation details

### Concurrency model

The package uses a single thread with an asyncio event loop to kick off requests and keep track of
the resources used.

However, threads are also in use:
- each call is actually executed in a thread pool, to avoid blocking the Runner
  (if the client passed to the Runner is synchronous/blocking)
- Runner.run(), spawns a new thread and a new event loop to run the main Runner logic in
 (`run_coro()`). This serves two objectives:
  - having the same sync entrypoint for both sync and async contexts (e.g. run the same code
    in a notebook and in a script)
  - gracefully handling `KeyboardInterrupt`



## Development and testing
Install the package in editable mode with `pip install -e .[test, lint]`

To quickly run the whole test suite, run the following in the root directory of the project:
```shell
pytest -n 8  # or another number of workers
```
This uses pytest-xdist to run tests in parallel, but will not support `--pdb` or verbose output.


To debug tests in detail, examine the usage of resources etc, run:
```shell
pytest --log-cli-level="DEBUG" --pdb -k name_of_test
```

### Linting and formatting
Format:
```shell
isort . && black .
```

Check:
```shell
flake8 && black --check . && mypy .
```

## TODOs:
- make it easier to import things; perhaps dedicated runner classes? (OpenAIChatRunner etc)
- more ready-made API descriptions - incl. batched ones?
- examples of using each pre-made API description
- fix the "interrupt and resume" test in Python 3.11
### Nice to have:
- (optional) slow start feature - pace the initial requests, instead of sending them all at once
- better utilization of APIs with a "gradual" quota growth, like OpenAI
- text-based logging if tqdm is not installed
- if/where possible, detect RateLimitExceeded - notify the user, slow down
- support "streaming" and/or continuous operation:
  - enable scheduling calls while running and/or getting inputs from generators
  - support "streaming" results - perhaps similar to "as_completed" in asyncio?
- support async calls (for people who prefer openai's acreate etc)
- add timeouts option? (for now, the user is responsible for handling timeouts)
- OpenAI shares information about rate limits in http response headers - could it be used without
  coupling too tightly with their API?
- tests (and explicit support?) for different ways of registering usage (time of request
  vs time of completion vs gradual)
- more robust wrapper-like behavior of schedule() - more complete support of VS Code
