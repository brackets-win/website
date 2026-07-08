"""Process-local single-flight: one caller computes, peers wait for the same result."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class _Flight:
    __slots__ = ("event", "result", "error", "waiters")

    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: object | None = None
        self.error: BaseException | None = None
        self.waiters = 0


_lock = threading.Lock()
_inflight: dict[str, _Flight] = {}


def single_flight(key: str, compute: Callable[[], T]) -> T:
    """
    Deduplicate concurrent identical work in this process.

    The first caller for ``key`` runs ``compute``; later callers with the same
    key block until that finishes and then receive the same return value (or
    the same exception). Does not change what is computed — only how many times.
    """
    with _lock:
        flight = _inflight.get(key)
        if flight is None:
            flight = _Flight()
            _inflight[key] = flight
            leader = True
        else:
            flight.waiters += 1
            leader = False

    if leader:
        try:
            result = compute()
            flight.result = result
            return result
        except BaseException as exc:
            flight.error = exc
            raise
        finally:
            flight.event.set()
            with _lock:
                # Keep the flight until waiters finish reading result/error.
                if flight.waiters == 0:
                    _inflight.pop(key, None)

    flight.event.wait()
    try:
        if flight.error is not None:
            raise flight.error
        return flight.result  # type: ignore[return-value]
    finally:
        with _lock:
            flight.waiters -= 1
            if flight.waiters <= 0 and flight.event.is_set():
                _inflight.pop(key, None)
