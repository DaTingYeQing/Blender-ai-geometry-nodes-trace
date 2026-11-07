# -*- coding: utf-8 -*-
"""frag2 示例：碎片数量和种子各取两种，触发四次求值。"""

TARGET = {
    "blend": r"C:\Users\zjn13\Desktop\PI_work\blender ai geo\破碎修改器.blend",
    "object": "破碎立方体",
    "modifier": "破碎",
    "param": "碎片数量",
    "node_tree": "",
}


def _input_id(ctx, display):
    for item in ctx.node_tree.interface.items_tree:
        if getattr(item, "item_type", "") != "SOCKET":
            continue
        if getattr(item, "in_out", "") != "INPUT":
            continue
        if item.name == display:
            return item.identifier
    raise RuntimeError("input not found: %r" % display)


def evaluate(ctx):
    seed_id = _input_id(ctx, "种子")
    for count in (20, 40):
        for seed in (0, 7):
            ctx.mod[ctx.param_id] = count
            ctx.mod[seed_id] = seed
            ctx.obj.update_tag()
            t0 = time.perf_counter()
            ctx.bpy.context.view_layer.update()
            ms = (time.perf_counter() - t0) * 1000.0
            print("碎片数量 = %s  种子 = %s  实例数: %d  (%.3f ms)"
                  % (count, seed, ctx.instance_count(), ms))
