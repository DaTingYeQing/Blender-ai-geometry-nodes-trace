# -*- coding: utf-8 -*-

import os
import tempfile
import unittest
from unittest.mock import patch

import engine
import registry
from cards.base import CardContext


class FakeCard:
    def __init__(self, name, calls, needs=(), product=None):
        self.name = name
        self.needs = needs
        self.calls = calls
        self.product = product

    def build(self, ctx):
        self.calls.append(self.name)
        if self.product:
            with open(ctx.publish(self.product), "w", encoding="utf-8") as fh:
                fh.write(self.name)
        return {"name": self.name}


def make_context(root, products, test=False):
    work_dir = os.path.join(root, "work")
    out_dir = os.path.join(root, "out")
    os.makedirs(work_dir)
    os.makedirs(out_dir)
    return CardContext(
        work_dir, out_dir, {}, "node", {}, "blender", "pdb", {},
        products, test=test)


class RegistryTests(unittest.TestCase):
    def test_default_registration_is_complete(self):
        keys = [key for item in registry.CARDS for key in item.products]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(key in registry.PRODUCTS for key in keys))
        paths = [registry.PRODUCTS[key].path for key in keys]
        self.assertEqual(len(paths), len(set(paths)))
        for path in paths:
            self.assertFalse(os.path.isabs(path))
            self.assertNotIn("..", path.replace("\\", "/").split("/"))

    def test_context_uses_registered_paths(self):
        products = {
            "edge": registry.Product("graphs/edge.json"),
            "disasm": registry.Product("details/disasm.json", internal=True),
        }
        with tempfile.TemporaryDirectory() as root:
            ctx = make_context(root, products)
            self.assertEqual(
                ctx.out("edge"),
                os.path.join(ctx.out_dir, "graphs", "edge.json"))
            self.assertEqual(
                ctx.publish("disasm"),
                os.path.join(ctx.out_dir, "_internal", "details", "disasm.json"))

            debug_ctx = make_context(os.path.join(root, "debug"), products, test=True)
            self.assertEqual(
                debug_ctx.publish("disasm"),
                os.path.join(debug_ctx.out_dir, "details", "disasm.json"))

    def test_cards_consume_logical_products(self):
        products = {
            "first": registry.Product("nested/first.json"),
            "second": registry.Product("details/second.json", internal=True),
        }
        calls = []
        registrations = [
            registry.CardRegistration(
                FakeCard("first", calls, product="first"), ("first",)),
            registry.CardRegistration(
                FakeCard("second", calls, needs=("first",), product="second"),
                ("second",)),
        ]
        with tempfile.TemporaryDirectory() as root:
            ctx = make_context(root, products)
            with patch.object(registry, "CARDS", registrations):
                data = engine._run_cards(ctx, {})

            self.assertEqual(calls, ["first", "second"])
            self.assertEqual(data["products"], {"first": "nested/first.json"})
            self.assertEqual(data["cards"][0]["output"], "nested/first.json")
            self.assertTrue(data["cards"][0]["public"])
            self.assertEqual(data["cards"][1]["output"], "details/second.json")
            self.assertFalse(data["cards"][1]["public"])
            self.assertTrue(os.path.isfile(ctx.input("second")))

    def test_test_mode_publishes_internal_products(self):
        products = {"debug": registry.Product("details/debug.json", internal=True)}
        registrations = [
            registry.CardRegistration(
                FakeCard("debug", [], product="debug"), ("debug",)),
        ]
        with tempfile.TemporaryDirectory() as root:
            ctx = make_context(root, products, test=True)
            with patch.object(registry, "CARDS", registrations):
                data = engine._run_cards(ctx, {})
            self.assertEqual(
                data["products"], {"debug": "details/debug.json"})
            self.assertTrue(os.path.isfile(ctx.out("debug")))

    def test_missing_dependency_stops_the_pipeline(self):
        products = {"result": registry.Product("result.json")}
        calls = []
        registrations = [
            registry.CardRegistration(
                FakeCard("result", calls, needs=("missing",)), ("result",)),
        ]
        with tempfile.TemporaryDirectory() as root:
            ctx = make_context(root, products)
            with patch.object(registry, "CARDS", registrations):
                with self.assertRaisesRegex(RuntimeError, "missing inputs"):
                    engine._run_cards(ctx, {})
        self.assertEqual(calls, [])

    def test_missing_registered_output_is_an_error(self):
        products = {"result": registry.Product("result.json")}
        registrations = [
            registry.CardRegistration(FakeCard("result", []), ("result",)),
        ]
        with tempfile.TemporaryDirectory() as root:
            ctx = make_context(root, products)
            with patch.object(registry, "CARDS", registrations):
                with self.assertRaisesRegex(RuntimeError, "did not produce"):
                    engine._run_cards(ctx, {})


if __name__ == "__main__":
    unittest.main()
