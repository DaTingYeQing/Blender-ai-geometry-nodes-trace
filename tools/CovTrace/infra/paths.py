# -*- coding: utf-8 -*-
"""Filesystem helpers for CovTrace."""

import os
import re

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def norm(path):
    if not path:
        return ""
    return os.path.normpath(os.path.abspath(path))


def safe_name(name):
    """Turn a node name into a filesystem-safe directory name."""
    value = _SAFE.sub("_", (name or "").strip()).strip("._")
    return value or "node"


def file_fingerprint(path):
    """Cheap build identity: normalized path + size + mtime."""
    if not path or not os.path.isfile(path):
        return ""
    st = os.stat(path)
    return "%s:%d:%d" % (norm(path).replace("\\", "/"), st.st_size, st.st_mtime_ns)


def pdb_for(blender):
    # The exe embeds the PDB name "blender_private.pdb"; dbghelp only finds that name.
    # Prefer it so the run-key fingerprint matches the PDB dbghelp actually loads.
    private = os.path.join(os.path.dirname(blender), "blender_private.pdb")
    if os.path.isfile(private):
        return private
    stem, _ = os.path.splitext(blender)
    return stem + ".pdb"
