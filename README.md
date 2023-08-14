# rate_limited

A lightweight package meant to enable **efficient use of slow, rate-limited APIs** - like
those of Large Language Models (LLMs).

## Features
- parallel execution - be as quick as possible within the rate limit you have
- retry failed requests
- if interrupted (`KeyboardInterrupt`) e.g. in a notebook:
   - returns partial results
  - if ran again, continues from where it left off - and returns full results
- rate limits of some popular APIs already described - custom ones easy to add
- no dependencies (will use tqdm progress bars if installed)


## Assumptions:
- the client:
  - handles timeouts (requests will not hang forever)
  - raises an exception if the request fails (or the server returns an error / an "invalid" response)
- requests are independent from each other, do not rely on order, can be retried if failed
- the server verifies rate limits when it gets the request, records usage of resources upon
  completion - right before returning the results (this is a pessimistic assumption).
- we want a standard, simple interface for the user - working the same way in a script and in a
  notebook (+ most data scientists do not want to deal with asyncio). Therefore, `Runner.run()` is
  a blocking call, with the same behavior regardless of the context.
- async use is also supported - via `run_coro()` - but it will not support `KeyboardInterrupt`
  handling.

## Usage
In short:
- wrap your function with a `Runner()`, describing the rate limits you have
- call `Runner.schedule()` to schedule a request
- call `Runner.run()` to run the scheduled requests, get the results and any exceptions raised

### Installation
```shell
pip install rate_limited
```

### OpenAI example
```python
import openai
from rate_limited.runner import Runner
from rate_limited.apis.openai import chat

openai.api_key = "YOUR_API_KEY"
endpoint = "https://api.openai.com/v1/chat/completions"
model = "gpt-3.5-turbo"

# describe your rate limits - values based on https://platform.openai.com/account/rate-limits
resources = chat.openai_chat_resources(
    requests_per_minute=3_500,
    tokens_per_minute=90_000,
    model_max_len=4096,  # property of the model version in use - max sequence length
)
runner = Runner(openai.ChatCompletion.create, resources, max_concurrent=32)

topics = ["honey badgers", "llamas", "pandas"]
for topic in topics:
    messages = [{"role": "user", "content": f"Please write a poem about {topic}"}]
    # call runner.schedule exactly like you would call openai.CharCompletion.create
    runner.schedule(model=model, messages=messages, max_tokens=256, request_timeout=60)

results, exceptions = runner.run()
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

### Limiting the number of concurrent requests

The `max_concurrent` argument of `Runner` controls the number of concurrent requests.

### More advanced usage
See `apis.openai.chat` for an example of a more complex API description, with multiple resources 


## Implementation details

### Concurency model

The package uses a single thread with an asyncio event loop to kick off requests and keep track of
the resources used.

However, threads are also in use:
- each call is actually executed in a thread pool, to avoid blocking the Runner
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
- improved README and usage examples
- more ready-made API descriptions - incl. batched ones?
- fix the "interrupt and resume" test in Python 3.11
### Nice to have:
- add an optional "result verification" mechanism, for when the server might return, but 
  the results might be incorrect (e.g. LM not conforming with the given format) - so we retry
- have Runner.schedule show the docstring of the wrapped function, so that the user can see
  the arguments and their defaults
- (optional) slow start feature - pace the initial requests, instead of sending them all at once
- right now, if the API is responding quickly, we have a burst of progress, then a long wait
  (for the quota to renew), then another burst of progress. Either make this smoother (as above)
  or inform the user about the progress better (write a message if expecting to wait for a long
  time before the next batch of results)
- if/where possible, detect RateLimitExceeded - notify the user, slow down
- should runner.schedule return futures and enable "streaming" of results?
- add timeouts option? (for now, the user is responsible for handling timeouts)
- OpenAI shares information about rate limits in http response headers - could it be used without
  coupling too tightly with their API?
- tests (and explicit support?) for different ways of registering usage
- tests with and without tqdm installed, somehow (CI + different environments? patching?)
