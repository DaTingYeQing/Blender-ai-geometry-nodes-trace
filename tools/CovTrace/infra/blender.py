# -*- coding: utf-8 -*-
"""Host-side Blender process launcher."""

import subprocess

import directories


def command(blender, eval_path, work_dir, node, blend="", obj="", mod="", param="",
            gates="", phase="", measure_node=""):
    """The blend is opened by bootstrap from TARGET before the window opens."""
    cmd = [
        blender, "--background",
        "--python", directories.BOOTSTRAP_SCRIPT,
        "--",
        "--eval", eval_path,
        "--work", work_dir,
        "--node", node,
    ]
    if gates:
        cmd += ["--gates", gates]
    for flag, value in (
        ("--blend", blend),
        ("--obj", obj),
        ("--mod", mod),
        ("--param", param),
        ("--phase", phase),
        ("--measure-node", measure_node),
    ):
        if value:
            cmd += [flag, value]
    return cmd


def run(cmd, env=None):
    print(">>", " ".join(cmd))
    return subprocess.run(
        cmd, text=True, encoding="utf-8", errors="replace", env=env
    )
