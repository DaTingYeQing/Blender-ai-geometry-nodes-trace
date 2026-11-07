# -*- coding: utf-8 -*-
"""Wrap a Graphviz SVG in a self-contained HTML viewer.

Search matches only the node label that is visible in the graph (plain
case-insensitive substring). Drag to pan, wheel to zoom.

Usage:
  python tools/svg_viewer.py 7343650d            # -> <run>/full.html or newest .svg
  python tools/svg_viewer.py 7343650d --name full
  python tools/svg_viewer.py --svg out/diff/full.svg
"""

import argparse
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import directories

HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta http-equiv="Cache-Control" content="no-store">
<title>__TITLE__</title>
<style>
  html, body { margin:0; height:100%; overflow:hidden; background:#fafafa;
               font:13px/1.4 Consolas, "Segoe UI", sans-serif; }
  #bar { position:fixed; z-index:10; left:0; right:0; top:0; height:42px;
         display:flex; align-items:center; gap:8px; padding:0 10px;
         background:#fff; border-bottom:1px solid #d0d0d0; box-sizing:border-box; }
  #bar input { width:380px; padding:5px 8px; border:1px solid #aaa;
               border-radius:4px; outline:none; font:13px Consolas, monospace; }
  #bar input:focus { border-color:#e65100; box-shadow:0 0 0 2px #ffe0b2; }
  #bar button { padding:4px 9px; border:1px solid #bbb; border-radius:4px;
                background:#f6f6f6; cursor:pointer; font-size:12px; }
  #bar button:hover { background:#eee; }
  #count { color:#555; min-width:90px; }
  #hint { color:#999; font-size:11px; }
  #panel { position:fixed; z-index:9; top:42px; right:0; bottom:26px; width:340px;
           background:#fff; border-left:1px solid #d0d0d0; overflow:auto;
           display:none; box-sizing:border-box; }
  #panel.open { display:block; }
  #panel .row { padding:5px 8px; border-bottom:1px solid #eee; cursor:pointer;
                word-break:break-all; }
  #panel .row:hover { background:#fff3e0; }
  #panel .row.sel { background:#ffe0b2; }
  #viewport { position:absolute; left:0; right:0; top:42px; bottom:26px;
              overflow:hidden; cursor:grab; }
  #viewport.dragging { cursor:grabbing; }
  #wrap { position:absolute; left:0; top:0; transform-origin:0 0;
          will-change: transform; }
  #wrap svg { display:block; pointer-events:none; }
  svg.dragging g.edge { visibility:hidden; }
  #current { position:fixed; z-index:11; left:0; right:0; bottom:0; height:26px;
             line-height:26px; padding:0 10px; background:#263238; color:#eceff1;
             font-size:12px; white-space:nowrap; overflow:hidden;
             text-overflow:ellipsis; box-sizing:border-box; }
  g.node path, g.node polygon { fill:#dbeafe !important; stroke:#2563eb !important; }
  g.node text { fill:#0f172a !important; }
  g.node.hl path, g.node.hl polygon { fill:#e53935 !important; stroke:#b71c1c !important;
                                      stroke-width:2 !important; }
  g.node.hl text { fill:#fff !important; }
  g.node.sel path, g.node.sel polygon { fill:#b71c1c !important; stroke:#7f1d1d !important;
                                        stroke-width:3 !important; }
  g.node.sel text { fill:#fff !important; font-weight:bold; }
  mark { background:#ffb300; color:#000; padding:0 1px; }
</style>
</head>
<body>
<div id="bar">
  <input id="q" type="text" placeholder="按图上显示的名字搜索（不区分大小写）" autofocus>
  <span id="count">—</span>
  <button id="prev" title="上一个 (Shift+Enter)">↑</button>
  <button id="next" title="下一个 (Enter)">↓</button>
  <button id="list" title="显示/隐藏结果列表">列表</button>
  <button id="fit" title="适应窗口">适应</button>
  <button id="reset" title="100%">1:1</button>
  <span id="hint">v4 连续子串 · 拖动平移/缩放 · Esc 清除</span>
</div>
<div id="panel"></div>
<div id="current"></div>
<div id="viewport"><div id="wrap">
__SVG__
</div></div>
<script>
(function () {
  var svg = document.querySelector('#wrap svg');
  var viewport = document.getElementById('viewport');
  var wrap = document.getElementById('wrap');
  var q = document.getElementById('q');
  var count = document.getElementById('count');
  var panel = document.getElementById('panel');
  var currentBar = document.getElementById('current');

  var vb = svg.viewBox.baseVal;
  if (vb && vb.width) {
    svg.setAttribute('width', vb.width);
    svg.setAttribute('height', vb.height);
    svg.style.width = vb.width + 'px';
    svg.style.height = vb.height + 'px';
  } else {
    vb = { x: 0, y: 0, width: svg.getBBox().width, height: svg.getBBox().height };
  }

  var XLINK = 'http://www.w3.org/1999/xlink';
  var nodes = [];
  var allNodes = svg.querySelectorAll('g.node');
  for (var i = 0; i < allNodes.length; i++) {
    var g = allNodes[i];
    var texts = g.querySelectorAll('text');
    var label = [];
    for (var t = 0; t < texts.length; t++) label.push(texts[t].textContent);
    var a = g.querySelector('a');
    var full = a ? (a.getAttributeNS(XLINK, 'title') ||
                    a.getAttribute('xlink:title') || '') : '';
    nodes.push({
      el: g,
      label: label.join(' '),
      lower: label.join(' ').toLowerCase(),
      full: full || label.join(' ')
    });
  }

  var matches = [];
  var hlNodes = [];
  var current = -1;
  var needle = '';
  var scale = 1, tx = 0, ty = 0;

  function apply() {
    wrap.style.transform = 'translate3d(' + tx + 'px,' + ty + 'px,0) scale(' + scale + ')';
  }

  function fit() {
    var w = viewport.clientWidth, h = viewport.clientHeight;
    scale = Math.min(w / vb.width, h / vb.height) * 0.98;
    if (!isFinite(scale) || scale <= 0) scale = 1;
    tx = (w - vb.width * scale) / 2 - vb.x * scale;
    ty = (h - vb.height * scale) / 2 - vb.y * scale;
    apply();
  }

  function zoomAt(cx, cy, factor) {
    var next = Math.max(0.002, Math.min(40, scale * factor));
    var k = next / scale;
    tx = cx - (cx - tx) * k;
    ty = cy - (cy - ty) * k;
    scale = next;
    apply();
  }

  function focus(node) {
    if (scale < 0.35) {
      var bb = node.el.getBBox();
      scale = Math.min(2.5, Math.max(0.55, 144 / Math.max(bb.width, 1)));
      if (!isFinite(scale) || scale <= 0) scale = 0.8;
      apply();
    }
    var r = node.el.getBoundingClientRect();
    var v = viewport.getBoundingClientRect();
    tx += v.left + v.width / 2 - (r.left + r.width / 2);
    ty += v.top + v.height / 2 - (r.top + r.height / 2);
    apply();
  }

  function markHtml(raw) {
    var lower = raw.toLowerCase();
    var at = lower.indexOf(needle);
    if (at < 0) return escapeHtml(raw);
    return escapeHtml(raw.slice(0, at)) + '<mark>' +
           escapeHtml(raw.slice(at, at + needle.length)) + '</mark>' +
           escapeHtml(raw.slice(at + needle.length));
  }

  function escapeHtml(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function clearMarks() {
    for (var i = 0; i < hlNodes.length; i++) {
      hlNodes[i].el.classList.remove('hl', 'sel');
    }
    hlNodes = [];
    matches = [];
    current = -1;
    panel.innerHTML = '';
    panel.classList.remove('open');
    currentBar.textContent = '';
  }

  function renderPanel() {
    panel.innerHTML = '';
    var limit = Math.min(matches.length, 200);
    for (var i = 0; i < limit; i++) {
      (function (idx) {
        var node = nodes[idx];
        var row = document.createElement('div');
        row.className = 'row';
        row.innerHTML = markHtml(node.label);
        row.title = node.full;
        row.addEventListener('click', function () { select(idx, false); });
        panel.appendChild(row);
      })(matches[i]);
    }
    if (matches.length > limit) {
      var more = document.createElement('div');
      more.className = 'row';
      more.textContent = '还有 ' + (matches.length - limit) + ' 条未列出';
      panel.appendChild(more);
    }
  }

  function select(pos, scroll) {
    if (pos < 0 || pos >= matches.length) return;
    if (current >= 0 && current < matches.length) {
      nodes[matches[current]].el.classList.remove('sel');
    }
    current = pos;
    var node = nodes[matches[pos]];
    node.el.classList.add('sel');
    count.textContent = (pos + 1) + ' / ' + matches.length;
    currentBar.textContent = node.full;
    if (scroll) focus(node);
    var rows = panel.querySelectorAll('.row');
    for (var i = 0; i < rows.length; i++) rows[i].classList.remove('sel');
    if (pos < rows.length) {
      rows[pos].classList.add('sel');
      rows[pos].scrollIntoView({ block: 'nearest' });
    }
  }

  var timer = null;
  function runSearch() {
    clearMarks();
    needle = q.value.trim().toLowerCase();
    if (!needle) {
      count.textContent = '—';
      return;
    }
    var found = [];
    for (var i = 0; i < nodes.length; i++) {
      var at = nodes[i].lower.indexOf(needle);
      if (at >= 0) found.push({ i: i, at: at, len: nodes[i].label.length });
    }
    found.sort(function (a, b) {
      return a.at - b.at || a.len - b.len || a.i - b.i;
    });
    matches = found.map(function (x) { return x.i; });
    current = -1;
    if (!matches.length) {
      count.textContent = '0 个匹配';
      return;
    }
    for (var m = 0; m < matches.length; m++) {
      hlNodes.push(nodes[matches[m]]);
      nodes[matches[m]].el.classList.add('hl');
    }
    renderPanel();
    select(0, true);
  }

  q.addEventListener('input', function () {
    clearTimeout(timer);
    timer = setTimeout(runSearch, 120);
  });
  q.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (!matches.length) return;
      select((current + (e.shiftKey ? -1 : 1) + matches.length) % matches.length, true);
    } else if (e.key === 'Escape') {
      q.value = '';
      runSearch();
    }
  });
  document.getElementById('next').onclick = function () {
    if (matches.length) select((current + 1) % matches.length, true);
  };
  document.getElementById('prev').onclick = function () {
    if (matches.length) select((current - 1 + matches.length) % matches.length, true);
  };
  document.getElementById('list').onclick = function () {
    panel.classList.toggle('open');
  };
  document.getElementById('fit').onclick = fit;
  document.getElementById('reset').onclick = function () { scale = 1; tx = 0; ty = 0; apply(); };
  window.addEventListener('resize', fit);
  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'f') {
      e.preventDefault(); q.focus(); q.select();
    }
  });

  var dragging = false, lastX = 0, lastY = 0;
  viewport.addEventListener('pointerdown', function (e) {
    if (e.button !== 0) return;
    dragging = true; lastX = e.clientX; lastY = e.clientY;
    viewport.classList.add('dragging');
    svg.classList.add('dragging');
    viewport.setPointerCapture(e.pointerId);
  });
  viewport.addEventListener('pointermove', function (e) {
    if (!dragging) return;
    tx += e.clientX - lastX; ty += e.clientY - lastY;
    lastX = e.clientX; lastY = e.clientY;
    apply();
  });
  viewport.addEventListener('pointerup', function (e) {
    dragging = false; viewport.classList.remove('dragging');
    svg.classList.remove('dragging');
    try { viewport.releasePointerCapture(e.pointerId); } catch (err) {}
  });
  viewport.addEventListener('wheel', function (e) {
    e.preventDefault();
    var r = viewport.getBoundingClientRect();
    zoomAt(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.18 : 1 / 1.18);
  }, { passive: false });

  requestAnimationFrame(fit);
})();
</script>
</body>
</html>
"""


def build(svg_path, title):
    with open(svg_path, encoding="utf-8") as fh:
        text = fh.read()
    text = re.sub(r"<\?xml[^>]*\?>\s*", "", text, count=1)
    text = re.sub(r"<!DOCTYPE[^>]*>\s*", "", text, count=1, flags=re.S)
    return HTML.replace("__SVG__", text).replace("__TITLE__", title)


def find_svg(hash8):
    exact = glob.glob(os.path.join(directories.OUT_DIR, "*", hash8, "*.svg"))
    if exact:
        return sorted(exact)
    return sorted(p for p in glob.glob(os.path.join(directories.OUT_DIR, "*", "*", "*.svg"))
                  if os.path.basename(os.path.dirname(p)).startswith(hash8))


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("hash8", nargs="?", help="run hash, e.g. 7343650d")
    ap.add_argument("--svg", default="", help="explicit .svg path")
    ap.add_argument("--name", default="",
                    help="svg basename when a run has several (e.g. full)")
    ap.add_argument("--out", default="", help="output .html path")
    ap.add_argument("--title", default="")
    a = ap.parse_args()

    if a.svg:
        svg_path = os.path.abspath(a.svg)
    elif a.hash8:
        matches = find_svg(a.hash8)
        if not matches:
            print("!! out/*/%s/*.svg 不存在；先运行 dot_graph.py %s -svg"
                  % (a.hash8, a.hash8), file=sys.stderr)
            return 2
        names = {os.path.splitext(os.path.basename(p))[0]: p for p in matches}
        if a.name:
            if a.name not in names:
                print("!! %s 下没有 %s.svg，可用: %s"
                      % (a.hash8, a.name, ", ".join(sorted(names))), file=sys.stderr)
                return 2
            svg_path = names[a.name]
        elif "full" in names:
            svg_path = names["full"]
        elif len(matches) == 1:
            svg_path = matches[0]
        else:
            svg_path = max(matches, key=os.path.getmtime)
            print(">> 多个 svg，使用最新的: %s" % svg_path)
    else:
        avail = sorted({os.path.basename(os.path.dirname(p))
                        for p in glob.glob(os.path.join(directories.OUT_DIR, "*", "*", "*.svg"))})
        print("!! 需要指定哈希，例如: python tools/svg_viewer.py 7343650d",
              file=sys.stderr)
        if avail:
            print("   可用: %s" % ", ".join(avail[-20:]), file=sys.stderr)
        return 2

    if not os.path.isfile(svg_path):
        print("!! svg not found: %s" % svg_path, file=sys.stderr)
        return 2
    out = a.out or os.path.splitext(svg_path)[0] + ".html"
    title = a.title or os.path.basename(svg_path)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(build(svg_path, title))
    print(">> svg : %s" % svg_path)
    print(">> html: %s (%.1f MB)" % (out, os.path.getsize(out) / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
