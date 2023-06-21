# rate_limited

A lightweight package meant to enable efficient, parallel use of slow, rate-limited APIs - like
those of LLMs.

The assumptions:
- requests are independent from each other, do not rely on order, can be retried if failed
- the server verifies rate limits when it gets the request, records usage of resources upon
  completion - right before returning the results (this is a pessimistic assumption).