# -*- coding: utf-8 -*-
"""Translation card interface and host-side context."""

import os


class CardContext:
    def __init__(self, work_dir, out_dir, target, node, manifest, blender, pdb, raw):
        self.work_dir = work_dir
        self.out_dir = out_dir
        self.target = target
        self.node = node
        self.manifest = manifest
        self.blender = blender
        self.pdb = pdb
        self.raw_paths = raw

    def raw(self, key):
        path = self.raw_paths.get(key)
        if not path or not os.path.isfile(path):
            raise RuntimeError("raw %r not found" % key)
        return path

    def out(self, name):
        return os.path.join(self.out_dir, name)


class TranslationCard:
    name = ""
    needs = ()

    def build(self, ctx):
        raise NotImplementedError
