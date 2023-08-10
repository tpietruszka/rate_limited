from functools import partial
from typing import List

from rate_limited.apis.common import get_requests_per_minute
from rate_limited.calls import Call
from rate_limited.resources import Resource


def openai_chat_resources(requests_per_minute, tokens_per_minute, model_max_len) -> List[Resource]:
    # getting too close to the limit results in some refusals (there are some differences between
    # in how the usage is tracked - hard to reverse-engineer exactly)
    # TODO: clean this up somehow? (getting a closer match to the behavior of the API)
    token_limit = int(tokens_per_minute * 0.95)
    return [
        get_requests_per_minute(requests_per_minute),
        get_tokens_per_minute(token_limit, model_max_len),
    ]


def get_tokens_per_minute(quota: int, model_max_len: int) -> Resource:
    estimator = partial(estimate_tokens_used, model_max_len=model_max_len)
    return Resource(
        name="tokens_per_minute",
        quota=quota,
        time_window_seconds=60,
        max_results_usage_estimator=estimator,
        results_usage_extractor=get_used_tokens,
    )


def get_used_tokens(results: dict) -> int:
    total_tokens = results.get("usage", {}).get("total_tokens", None)
    if total_tokens is None:
        raise ValueError("Could not find total_tokens in results")
    return total_tokens


def estimate_tokens_used(call: Call, model_max_len: int) -> int:
    """
    Estimate (upper bound) of how many tokens might be used by a request - before running it
    """
    max_tokens_arg = call.get_argument("max_tokens")
    n_arg = call.get_argument("n") or 1  # how many completions to return
    if max_tokens_arg is not None:
        max_tokens = estimate_input_tokens(call) + max_tokens_arg
    else:
        max_tokens = model_max_len
    return max_tokens * n_arg


def estimate_input_tokens(call: Call) -> int:
    parts = []
    for key in ["messages", "functions"]:
        array = call.get_argument(key) or []
        # fmt: off
        parts += [
            part
            for dct in array
            for part in dct.values()
            if isinstance(part, str)
        ]
        # fmt: on
    # very rough over-estimate - assuming 2 tokens per word
    tokens_uppoer_bound = sum(len(part.split(" ") * 2) for part in parts)
    # TODO: improve estimation - look into details of possible arguments
    # TODO: if installed, use tiktoken to count tokens exactly
    return tokens_uppoer_bound
