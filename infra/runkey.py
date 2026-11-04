# -*- coding: utf-8 -*-
"""Run identity: eval content + node + build fingerprint."""

import hashlib
import json

from . import paths

RUN_KEY_VERSION = b"covtrace-runkey-v1\0"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_fingerprint(blender, pdb):
    return paths.file_fingerprint(blender) + "|" + paths.file_fingerprint(pdb)


def run_key(eval_path, node, blender, pdb, target=None):
    h = hashlib.sha256()
    h.update(RUN_KEY_VERSION)
    with open(eval_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    h.update(b"\0")
    h.update(node.encode("utf-8"))
    h.update(b"\0")
    h.update(build_fingerprint(blender, pdb).encode("utf-8"))
    if target is not None:
        h.update(b"\0")
        h.update(json.dumps(target, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return h.hexdigest()


def short(key):
    return key[:8]
