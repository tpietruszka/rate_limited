from datetime import datetime
from typing import Optional


class ProgressBar:
    """A progress bar that uses tqdm if available - does nothing otherwise."""

    def __init__(self, total: int, long_wait_seconds: Optional[float] = None):
        try:
            from tqdm import tqdm

            self.pbar: Optional[tqdm] = tqdm(total=total)
        except ImportError:
            self.pbar = None

        self.long_wait_seconds = long_wait_seconds

    def set_state(self, num_completed: int, num_total: Optional[int] = 0):
        if self.pbar:
            self.pbar.update(num_completed - self.pbar.n)
            if num_total is not None:
                old_total = self.pbar.total
                self.pbar.total = num_total
                if old_total != num_total:
                    self.pbar.refresh()
        # TODO: optional text-based logging, perhaps at DEBUG level

    def update_long_wait_warning(self, waiting_until: Optional[datetime] = None, message: str = ""):
        """
        If an estimate of the time until the next progress is available and it is longer than
        self.long_wait_seconds, then show a message in the progress bar.
        """
        if self.long_wait_seconds is None:
            return
        if self.pbar is None:
            # TODO: optional text-based logging
            return
        remaining = (waiting_until - datetime.now()).total_seconds() if waiting_until else 0
        if remaining < self.long_wait_seconds:
            self.pbar.set_description("")
        else:
            self.pbar.set_description(f"{message}. Waiting for {remaining:.1f} seconds")
        self.pbar.refresh()

    def close(self):
        if self.pbar:
            self.pbar.close()
