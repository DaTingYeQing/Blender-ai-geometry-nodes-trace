# -*- coding: utf-8 -*-
"""Gate, translation card and product registration."""

from dataclasses import dataclass

from cards.base import TranslationCard
from cards.coverage import CoverageCard
from cards.diff import DiffCard
from cards.disasm import DisasmCard
from cards.edge import EdgeCard
from cards.filter import FilterCard
from cards.metrics import MetricsCard
from cards.timing import TimingCard
from gates.calls import CallsGate
from gates.coverage import CoverageGate


@dataclass(frozen=True)
class Product:
    path: str
    internal: bool = False
    cache: bool = False


@dataclass(frozen=True)
class CardRegistration:
    card: TranslationCard
    products: tuple[str, ...]


PRODUCTS = {
    "edge": Product("edge.json", cache=True),
    "disasm": Product("disasm.json", internal=True),
    "coverage": Product("coverage.json"),
    "timing": Product("timing.json", internal=True),
    "metrics": Product("functions.jsonl", cache=True),
    "filter": Product("filter.json", cache=True),
    "diff": Product("diff.json"),
}

GATES = [CoverageGate(), CallsGate()]
CARDS = [
    CardRegistration(EdgeCard(), ("edge",)),
    CardRegistration(DisasmCard(), ("disasm",)),
    CardRegistration(CoverageCard(), ("coverage",)),
    CardRegistration(TimingCard(), ("timing",)),
    CardRegistration(MetricsCard(), ("metrics",)),
    CardRegistration(FilterCard(), ("filter",)),
    CardRegistration(DiffCard(), ("diff",)),
]
