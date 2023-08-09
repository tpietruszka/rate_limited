import contextvars
import functools
from asyncio import CancelledError, events
from concurrent.futures import ThreadPoolExecutor
from typing import Callable


async def to_thread_in_pool(pool: ThreadPoolExecutor, func: Callable, /, *args, **kwargs):
    """Copy of asyncio.to_thread, but:
    - using a custom thread pool
    - not requiring Python 3.9
    - cancelling the future when the task is cancelled

    Asynchronously run function *func* in a separate thread.

    Any *args and **kwargs supplied for this function are directly passed
    to *func*. Also, the current :class:`contextvars.Context` is propagated,
    allowing context variables from the main thread to be accessed in the
    separate thread.

    Return a coroutine that can be awaited to get the eventual result of *func*.
    """
    loop = events.get_running_loop()
    ctx = contextvars.copy_context()
    func_call = functools.partial(ctx.run, func, *args, **kwargs)
    future = loop.run_in_executor(pool, func_call)
    try:
        return await future
    except CancelledError:
        future.cancel()  # TODO: this is just a precaution, should not be needed, remove?
        raise
