# -*- coding: utf-8 -*-

import argparse
import os
import tempfile
import unittest
from unittest.mock import patch

import engine


def make_args(eval_path, **overrides):
    values = {
        "eval": eval_path,
        "measure_node": "",
        "phase": "",
        "diff_against": "",
        "dry_run": False,
        "no_raw": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def write_eval(root, node=True):
    path = os.path.join(root, "eval.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('TARGET = {}\n')
        if node:
            fh.write('NODE = "设置位置"\n')
    return path


class AutoDiffTests(unittest.TestCase):
    def test_node_runs_before_after_and_diff(self):
        calls = []
        with tempfile.TemporaryDirectory() as root:
            eval_path = write_eval(root)
            before_cache = os.path.join(root, "before-cache")

            def fake_run(a, result=None):
                calls.append((a.phase, a.diff_against, a.measure_node))
                if a.phase == "before":
                    result["cache_dir"] = before_cache
                return 0

            with patch.object(engine, "_run_once", fake_run):
                code = engine.run(make_args(eval_path))

        self.assertEqual(code, 0)
        self.assertEqual(calls, [
            ("before", "", "设置位置"),
            ("after", before_cache, "设置位置"),
        ])

    def test_no_node_keeps_single_capture(self):
        calls = []
        with tempfile.TemporaryDirectory() as root:
            eval_path = write_eval(root, node=False)

            def fake_run(a, result=None):
                calls.append(a.phase)
                return 0

            with patch.object(engine, "_run_once", fake_run):
                code = engine.run(make_args(eval_path))

        self.assertEqual(code, 0)
        self.assertEqual(calls, [""])

    def test_explicit_phase_keeps_single_capture(self):
        calls = []
        with tempfile.TemporaryDirectory() as root:
            eval_path = write_eval(root)

            def fake_run(a, result=None):
                calls.append(a.phase)
                return 0

            with patch.object(engine, "_run_once", fake_run):
                code = engine.run(make_args(eval_path, phase="before"))

        self.assertEqual(code, 0)
        self.assertEqual(calls, ["before"])

    def test_no_raw_removes_before_cache_after_diff(self):
        calls = []
        with tempfile.TemporaryDirectory() as root:
            eval_path = write_eval(root)
            before_cache = os.path.join(root, "before-cache")

            def fake_run(a, result=None):
                calls.append((a.phase, a.no_raw))
                if a.phase == "before":
                    os.makedirs(before_cache)
                    result["cache_dir"] = before_cache
                return 0

            with patch.object(engine, "_run_once", fake_run):
                code = engine.run(make_args(eval_path, no_raw=True))
            self.assertFalse(os.path.exists(before_cache))

        self.assertEqual(code, 0)
        self.assertEqual(calls, [("before", False), ("after", True)])

    def test_before_failure_stops_after(self):
        calls = []
        with tempfile.TemporaryDirectory() as root:
            eval_path = write_eval(root)

            def fake_run(a, result=None):
                calls.append(a.phase)
                return 1

            with patch.object(engine, "_run_once", fake_run):
                code = engine.run(make_args(eval_path))

        self.assertEqual(code, 1)
        self.assertEqual(calls, ["before"])


if __name__ == "__main__":
    unittest.main()
