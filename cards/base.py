# -*- coding: utf-8 -*-
"""Translation card interface: runs on the host and writes one JSON product."""


class TranslationCard:
    name = ""
    needs = ()

    def build(self, ctx):
        raise NotImplementedError
