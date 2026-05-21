import time
from contextlib import contextmanager


@contextmanager
def timed(label: str = ""):
    t0 = time.perf_counter()
    state = {"ms": 0}
    try:
        yield state
    finally:
        state["ms"] = int((time.perf_counter() - t0) * 1000)
