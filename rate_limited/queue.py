from asyncio import Queue


class CompletionTrackingQueue(Queue):
    def all_tasks_done(self) -> bool:
        """
        Return True if the queue is empty and task_done() was called for every item that had been
        put() into the queue.

        This is different than Queue.empty() which returns True if each put() was matched by
        a get(), but might still be waiting for task_done() to be called.
        """
        return self._unfinished_tasks == 0  # type: ignore
