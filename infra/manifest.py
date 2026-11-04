# -*- coding: utf-8 -*-
"""run.json helpers and duplicate/conflict classification."""

import json
import os
import time

from . import paths


def manifest_path(run_dir):
    return os.path.join(run_dir, "run.json")


def load(run_dir):
    path = manifest_path(run_dir)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write(run_dir, data):
    os.makedirs(run_dir, exist_ok=True)
    path = manifest_path(run_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(tmp, path)


def classify(run_dir, key):
    """Return new / duplicate / conflict / incomplete."""
    if not os.path.isdir(run_dir):
        return "new"
    data = load(run_dir)
    if data is None:
        return "incomplete"
    return "duplicate" if data.get("run_key") == key else "conflict"


def base(run_key, hash8, node, eval_path, blend, blender, pdb):
    return {
        "schema": 1,
        "run_key": run_key,
        "hash8": hash8,
        "node": node,
        "eval": paths.norm(eval_path),
        "blend": paths.norm(blend),
        "blender": paths.norm(blender),
        "pdb": paths.norm(pdb),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "gates": {},
        "cards": {},
        "counts": {},
    }
