"""Process-local single-flight helper tests."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
import unittest

from brackets.utils.single_flight import single_flight


class SingleFlightTests(unittest.TestCase):
    def test_concurrent_callers_share_one_compute(self):
        started = Event()
        release = Event()
        calls = {"n": 0}

        def compute():
            calls["n"] += 1
            started.set()
            release.wait(timeout=2)
            return "ok"

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(single_flight, "k-shared", compute) for _ in range(4)
            ]
            self.assertTrue(started.wait(timeout=2))
            release.set()
            results = [f.result(timeout=2) for f in futures]

        self.assertEqual(calls["n"], 1)
        self.assertEqual(results, ["ok", "ok", "ok", "ok"])

    def test_separate_keys_compute_independently(self):
        calls = {"a": 0, "b": 0}

        def make(key):
            def compute():
                calls[key] += 1
                return key

            return compute

        self.assertEqual(single_flight("a", make("a")), "a")
        self.assertEqual(single_flight("b", make("b")), "b")
        self.assertEqual(calls, {"a": 1, "b": 1})
