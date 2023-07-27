# rate_limited

A lightweight package meant to enable efficient, parallel use of slow, rate-limited APIs - like
those of LLMs.

The assumptions:
- requests are independent from each other, do not rely on order, can be retried if failed
- the server verifies rate limits when it gets the request, records usage of resources upon
  completion - right before returning the results (this is a pessimistic assumption).
- timeouts are handled by the user - the package does not provide any timeouts (for now)


## Development and testing
Install the package in editable mode with `pip install -e .[test, lint]`

After installing dependencies, run `pytest` in the root directory of the project.

To debug tests in detail, examine the usage of resources etc, run:
```shell
pytest --log-cli-level="DEBUG"
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
- measure how OpenAI API registers resource usage - decide if we need to pre-allocate tokens
  and prioritize the estimation feature
- notifications about errors?
- real API description for one endpoint - OpenAI chat completions?
- better README - description of functionality
- usage examples
- CI - github actions
- PyPI package
- more API descriptions - incl. batched ones?

### Nice to have:
- add an optional "result verification" mechanism, for when the server might return, but 
  the results might be incorrect (e.g. LM not conforming with the given format) - so we retry
- handle cancellations from the user (`KeyboardInterrupt`) - cancel pending requests, return
  results of completed requests
- (optional) progress bar
- extractor for estimation of usage; perhaps rename things with "pre-allocation" and "post-"?
- if/where possible, detect RateLimitExceeded - notify the user, slow down
- should runner.schedule return futures and enable "streaming" of results?
- add timeouts? -> maybe not
