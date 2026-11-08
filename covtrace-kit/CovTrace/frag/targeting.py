# -*- coding: utf-8 -*-
"""Blender-side validation and group-output rewiring for one node."""

import re

ZONE_TYPES = {
    "GeometryNodeRepeatInput",
    "GeometryNodeRepeatOutput",
    "GeometryNodeSimulationInput",
    "GeometryNodeSimulationOutput",
    "GeometryNodeForeachGeometryElementInput",
    "GeometryNodeForeachGeometryElementOutput",
}


class TargetError(Exception):
    pass


def _collect_zones(tree, seen=None):
    if seen is None:
        seen = set()
    key = id(tree)
    if key in seen:
        return []
    seen.add(key)
    zones = []
    for node in tree.nodes:
        if node.bl_idname in ZONE_TYPES:
            zones.append({
                "tree": tree.name,
                "node": node.name,
                "type": node.bl_idname,
            })
        if node.bl_idname == "GeometryNodeGroup" and getattr(node, "node_tree", None):
            zones.extend(_collect_zones(node.node_tree, seen))
    return zones


def validate_zones(tree):
    zones = _collect_zones(tree)
    if zones:
        detail = ", ".join("%s(%s)" % (z["node"], z["type"]) for z in zones)
        raise TargetError("暂不支持包含 Repeat/Foreach/Simulation 区域: %s" % detail)


def find_measure_node(tree, spec):
    spec = (spec or "").strip()
    if not spec:
        raise TargetError("没有指定要测量的节点")
    nodes = list(tree.nodes)
    matched = [n for n in nodes
               if spec in (n.name, n.label, n.bl_idname)]
    if not matched:
        key = re.sub(r"[^a-z0-9]+", "", spec.lower())
        if key:
            matched = [
                n for n in nodes
                if key in re.sub(
                    r"[^a-z0-9]+", "",
                    (n.name + n.label + n.bl_idname).lower())
            ]
    if not matched:
        raise TargetError("节点树里找不到节点: %r" % spec)
    if len(matched) > 1:
        names = ", ".join("%s(%s)" % (n.name, n.bl_idname) for n in matched)
        raise TargetError("节点名不唯一: %s" % names)
    return matched[0]


def _is_geometry(socket):
    return getattr(socket, "type", "") in ("GEOMETRY", "NodeSocketGeometry")


def _geometry_sockets(node):
    inputs = [s for s in node.inputs if _is_geometry(s)]
    outputs = [s for s in node.outputs if _is_geometry(s)]
    return inputs, outputs


def _group_output_socket(tree):
    outputs = [n for n in tree.nodes if n.bl_idname == "NodeGroupOutput"]
    if len(outputs) != 1:
        raise TargetError("需要且只能有一个 Group Output，当前 %d 个" % len(outputs))
    sockets = [s for s in outputs[0].inputs if _is_geometry(s)]
    if len(sockets) != 1:
        raise TargetError("Group Output 需要且只能有一个几何输出，当前 %d 个" % len(sockets))
    return sockets[0]


class Measure:
    def __init__(self, tree, node, in_socket, out_socket, group_socket):
        self.tree = tree
        self.node = node
        self.in_socket = in_socket
        self.out_socket = out_socket
        self.group_socket = group_socket

    def describe(self):
        return {
            "node": self.node.name,
            "type": self.node.bl_idname,
            "input": self.in_socket.name if self.in_socket else None,
            "output": self.out_socket.name,
            "group_output": self.group_socket.name,
        }


def resolve(tree, spec):
    node = find_measure_node(tree, spec)
    inputs, outputs = _geometry_sockets(node)
    if len(outputs) != 1:
        raise TargetError(
            "节点 %r 需要正好一个几何输出，当前 %d 个" % (node.name, len(outputs)))
    if len(inputs) > 1:
        raise TargetError(
            "节点 %r 有 %d 个几何输入，v1 只支持最多一个" % (node.name, len(inputs)))
    return Measure(tree, node, inputs[0] if inputs else None,
                   outputs[0], _group_output_socket(tree))


def rewire(measure, phase):
    tree = measure.tree
    for link in list(measure.group_socket.links):
        tree.links.remove(link)

    if phase == "after":
        tree.links.new(measure.out_socket, measure.group_socket)
    elif phase == "before":
        source = measure.in_socket
        if source is not None and source.is_linked:
            tree.links.new(source.links[0].from_socket, measure.group_socket)
    else:
        raise TargetError("未知 phase: %r" % phase)

    tree.update_tag()
