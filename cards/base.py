# -*- coding: utf-8 -*-
"""Translation card interface and host-side context."""

import os


class CardContext:
    def __init__(self, work_dir, out_dir, target, node, manifest, blender, pdb, raw,
                 options=None, test=False):
        self.work_dir = work_dir
        self.out_dir = out_dir
        self.target = target
        self.node = node
        self.manifest = manifest
        self.blender = blender
        self.pdb = pdb
        self.raw_paths = raw
        self.options = options or {}
        self.test = test

    def raw(self, key):
        path = self.raw_paths.get(key)
        if not path or not os.path.isfile(path):
            raise RuntimeError("raw %r not found" % key)
        return path

    def out(self, name):
        return os.path.join(self.out_dir, name)

    def internal(self, name):
        path = os.path.join(self.out_dir, "_internal", name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def publish(self, name):
        return self.out(name) if self.test else self.internal(name)

    def input(self, name):
        path = os.path.join(self.out_dir, "_internal", name)
        return path if os.path.isfile(path) else self.out(name)


class TranslationCard:
    name = ""
    needs = ()

    def build(self, ctx):
        raise NotImplementedError
