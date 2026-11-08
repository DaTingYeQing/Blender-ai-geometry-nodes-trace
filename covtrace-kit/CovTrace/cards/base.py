# -*- coding: utf-8 -*-
"""Translation card interface and host-side context."""

import os

import directories


class CardContext:
    def __init__(self, work_dir, out_dir, target, node, manifest, blender, pdb, raw,
                 products, options=None, test=False):
        self.work_dir = work_dir
        self.out_dir = out_dir
        self.target = target
        self.node = node
        self.manifest = manifest
        self.blender = blender
        self.pdb = pdb
        self.raw_paths = raw
        self.products = products
        self.options = options or {}
        self.test = test

    def raw(self, key):
        path = self.raw_paths.get(key)
        if not path or not os.path.isfile(path):
            raise RuntimeError("raw %r not found" % key)
        return path

    def product(self, key):
        try:
            return self.products[key]
        except KeyError:
            raise RuntimeError("unregistered product %r" % key) from None

    def _path(self, key, internal):
        product = self.product(key)
        relative = product.path
        if product.cache:
            path = os.path.normpath(os.path.join(self.work_dir, relative))
        else:
            if internal:
                relative = os.path.join(directories.INTERNAL_DIR, relative)
            path = os.path.normpath(os.path.join(self.out_dir, relative))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return path

    def out(self, key):
        return self._path(key, False)

    def internal(self, key):
        return self._path(key, True)

    def publish(self, key):
        internal = self.product(key).internal and not self.test
        return self._path(key, internal)

    def input(self, key):
        return self.publish(key)


class TranslationCard:
    name = ""
    needs = ()

    def build(self, ctx):
        raise NotImplementedError
