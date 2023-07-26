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
