from asyncio import Queue
from typing import Any


class CompletionTrackingQueue(Queue):
    def __init__(self, maxsize: int = 0) -> None:
        super().__init__(maxsize=maxsize)
        self.all_tasks_count = 0
        self.tasks_done_count = 0

    def put_nowait(self, item: Any) -> None:
        super().put_nowait(item)
        self.all_tasks_count += 1

    def task_done(self) -> None:
        super().task_done()
        self.tasks_done_count += 1

    def all_tasks_done(self) -> bool:
        """
        Return True if the queue is empty and task_done() was called for every item that had been
        put() into the queue.

        This is different than Queue.empty() which returns True if each put() was matched by
        a get(), but might still be waiting for task_done() to be called.
        """
        return self.all_tasks_count == self.tasks_done_count
