# -*- coding: utf-8 -*-
"""frag2 示例：改「破碎」修改器的「碎片数量」两次，各触发一次求值。"""

TARGET = {
    "blend": r"C:\Users\zjn13\Desktop\PI_work\blender ai geo\破碎修改器.blend",
    "object": "破碎立方体",
    "modifier": "破碎",
    "param": "碎片数量",
    "node_tree": "",
}


def evaluate(ctx):
    for value in (20, 40):
        ms = ctx.set_value(value)
        print("碎片数量 = %s  实例数: %d  (%.3f ms)"
              % (value, ctx.instance_count(), ms))
