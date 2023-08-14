from typing import Optional


class ProgressBar:
    """A progress bar that uses tqdm if available - does nothing otherwise."""

    def __init__(self, total: int):
        try:
            from tqdm import tqdm

            self.pbar: Optional[tqdm] = tqdm(total=total)
        except ImportError:
            self.pbar = None

    def set_state(self, num_completed: int, num_total: Optional[int] = 0):
        if self.pbar:
            self.pbar.update(num_completed - self.pbar.n)
            if num_total is not None:
                old_total = self.pbar.total
                self.pbar.total = num_total
                if old_total != num_total:
                    self.pbar.refresh()
        # TODO: optional text-based logging, perhaps at DEBUG level

    def close(self):
        if self.pbar:
            self.pbar.close()
