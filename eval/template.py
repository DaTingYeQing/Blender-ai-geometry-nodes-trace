# -*- coding: utf-8 -*-
"""求值脚本模板：目标信息和业务求值都写在这里。

TARGET 必须是字面量字典（引擎会在宿主侧用 AST 读取，不执行脚本）。
TARGET["param"] 用显示名；底座负责解析成真正的 socket identifier。
"""

TARGET = {
    "blend": r"C:\Users\zjn13\Desktop\PI_work\blender ai geo\破碎修改器.blend",
    "object": "破碎立方体",
    "modifier": "破碎",
    "param": "碎片数量",
    "node_tree": "",  # 可选：只用于校验；留空表示用修改器的 node_group
}

# 要测量边界的节点：节点名、label 或 bl_idname 均可（如 "设置位置" / "setpos"）。
# v1 要求最多一个几何输入、正好一个几何输出；工程里不能有 Repeat/Foreach/Simulation 区域。
NODE = "设置位置"


def evaluate(ctx):
    for value in (20, 40):
        ms = ctx.set_value(value)
        print(value, ctx.instance_count(), "%.3f ms" % ms)
