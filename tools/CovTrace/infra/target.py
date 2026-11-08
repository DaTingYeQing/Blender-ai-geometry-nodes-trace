# -*- coding: utf-8 -*-
"""Read TARGET from an evaluation script without executing it on the host."""

import ast
import os

REQUIRED = ("blend", "object", "modifier")


class TargetError(Exception):
    pass


def load(eval_path):
    with open(eval_path, encoding="utf-8-sig") as fh:
        source = fh.read()
    try:
        tree = ast.parse(source, filename=eval_path)
    except SyntaxError as exc:
        raise TargetError("求值脚本语法错误: %s" % exc)

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for item in node.targets:
            if isinstance(item, ast.Name) and item.id == "TARGET":
                try:
                    value = ast.literal_eval(node.value)
                except ValueError:
                    raise TargetError("TARGET 必须是字面量字典（字符串值）")
                if not isinstance(value, dict):
                    raise TargetError("TARGET 必须是字典")
                return {str(k): v for k, v in value.items()}
    raise TargetError("求值脚本缺少 TARGET = {...}")


def measure_node(eval_path):
    """Read the optional NODE = "..." literal without executing the script."""
    with open(eval_path, encoding="utf-8-sig") as fh:
        source = fh.read()
    try:
        tree = ast.parse(source, filename=eval_path)
    except SyntaxError as exc:
        raise TargetError("求值脚本语法错误: %s" % exc)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for item in node.targets:
            if isinstance(item, ast.Name) and item.id == "NODE":
                try:
                    value = ast.literal_eval(node.value)
                except ValueError:
                    raise TargetError("NODE 必须是字符串字面量")
                if not isinstance(value, str):
                    raise TargetError("NODE 必须是字符串")
                return value
    return ""


def merge(target, blend="", obj="", mod="", param=""):
    out = dict(target)
    for key, value in (
        ("blend", blend),
        ("object", obj),
        ("modifier", mod),
        ("param", param),
    ):
        if value:
            out[key] = value
    return out


def validate(target):
    missing = [key for key in REQUIRED if not target.get(key)]
    if missing:
        raise TargetError("TARGET 缺少字段: " + ", ".join(missing))
    if not os.path.isfile(target["blend"]):
        raise TargetError("找不到工程: %s" % target["blend"])
    node_tree = target.get("node_tree", "")
    if node_tree and not isinstance(node_tree, str):
        raise TargetError("TARGET['node_tree'] 必须是字符串")
