"""repo-dissect 模板出图：JSON 数据 -> 确定性 SVG（只用 Python 标准库，Python 3.8+）。

layered(spec)   -> 分层架构 / 功能架构图（无连线的分层方块图）
corridor(spec)  -> 业务全景图（按场景成行的"场景走廊"，无交叉连线）

用法: python3 diagrams.py <layered|corridor> spec.json out.svg [--accent '#RRGGBB']
     （色值要加引号，否则 shell 会把 # 后面当注释）
"""
import html
import re

# ---- design tokens -------------------------------------------------------
T = {  # 设计令牌：中性色 + 一种强调色 + 一种状态色
    "ink": "#181D2B",       # 正文
    "muted": "#59627A",     # 次字
    "line": "#CCD2E0",      # 框线
    "band": "#F6F7FA",      # 分层底色
    "paper": "#FFFFFF",     # 卡片
    "accent": "#3B51D4",    # 强调色（默认靛蓝），唯一强调色；可用 --accent 替换
    "accent_bg": "#EEF1FE", # 强调色浅底
    "warn": "#A25E00",      # 状态标签文字
    "warn_bg": "#FCF0DC",   # 状态标签浅底
}
FONT = '-apple-system,"Segoe UI","PingFang SC","Noto Sans CJK SC","Microsoft YaHei",sans-serif'


def tw(s, size):
    """approximate text width: CJK ~1em, ASCII ~0.56em"""
    w = 0
    for ch in s:
        w += size if ord(ch) > 0x2E80 else size * 0.56
    return w


def esc(s):
    return html.escape(s, quote=True)


def text(x, y, s, size=13, color=None, weight=400, anchor="start"):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
            f'fill="{color or T["ink"]}" text-anchor="{anchor}" font-family=\'{FONT}\'>{esc(s)}</text>')


def tag(x, y, label, kind):
    """small status pill; returns (svg, width)"""
    color, bg = (T["warn"], T["warn_bg"]) if kind == "warn" else (T["accent"], T["accent_bg"])
    w = tw(label, 10) + 10
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="16" rx="8" fill="{bg}" stroke="{color}" stroke-width="0.8"/>'
            + text(x + w / 2, y + 11.5, label, 10, color, 500, "middle")), w


STATUS = {  # status -> (stroke dash, text color, pill label, pill kind)
    None: (None, None, None, None),
    "ee": ("4 3", T["muted"], "企业版", "warn"),
    "beta": (None, None, "实验性", "warn"),
    "focus": (None, None, None, None),
}


def module_box(x, y, w, h, m, quiet=False):
    name, sub, st = m.get("name"), m.get("sub"), m.get("status")
    dash, tcolor, pill, kind = STATUS.get(st, STATUS[None])
    pill = m.get("tag") or pill  # 自定义标签文案，如 "仅 Python"
    if quiet:  # group already labels the status: encode it once, not twice
        pill = None
    fill, stroke, sw = T["paper"], T["line"], 1
    if st == "focus":
        fill, stroke, sw = T["accent_bg"], T["accent"], 1.6
    out = [f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" fill="{fill}" '
           f'stroke="{stroke}" stroke-width="{sw}"' + (f' stroke-dasharray="{dash}"' if dash else "") + "/>"]
    cy = y + h / 2 + (-2 if sub else 4.5)
    out.append(text(x + w / 2, cy, name, 13, tcolor, 500, "middle"))
    if sub:
        out.append(text(x + w / 2, cy + 16, sub, 11, T["muted"], 400, "middle"))
    if pill:
        pw = tw(pill, 10) + 10
        s, _ = tag(x + w - 6 - pw, y - 8, pill, kind or "warn")
        out.append(s)
    return "\n".join(out)


def layered(spec, width=1040):
    """spec = {title, layers:[{name, groups:[{title?, dashed?, modules:[{name, sub?, status?, tag?}]}]}], legend?}"""
    LBL, PAD, GAP, BW_MIN, BH = 112, 16, 12, 150, 52
    inner = width - LBL - PAD * 2
    cols = max(1, int((inner + GAP) // (BW_MIN + GAP)))
    bw = (inner - GAP * (cols - 1)) / cols
    x0 = LBL + PAD
    bands, fg, y = [], [], 8
    for layer in spec["layers"]:
        ly0, cy = y, y + PAD + 4
        for gi, g in enumerate(layer["groups"]):
            if gi:
                cy += 6 + (14 if g.get("dashed") else 0)
            mods = g["modules"]
            rows = (len(mods) + cols - 1) // cols
            gy0 = cy
            if g.get("title"):
                fg.append(text(x0, cy + 6, g["title"], 11.5, T["warn"] if g.get("dashed") else T["muted"], 600))
                cy += 20
            for i, m in enumerate(mods):
                r, c = divmod(i, cols)
                fg.append(module_box(x0 + c * (bw + GAP), cy + r * (BH + GAP), bw, BH, m, quiet=bool(g.get("dashed"))))
            gh = rows * BH + (rows - 1) * GAP
            if g.get("dashed"):
                bands.append(f'<rect x="{x0 - 8}" y="{gy0 - 12}" width="{inner + 16:.1f}" height="{cy - gy0 + gh + 20:.1f}" '
                             f'rx="8" fill="#FFFCF5" stroke="{T["warn"]}" stroke-width="1" stroke-dasharray="5 4"/>')
                cy += 8
            cy += gh + 8
        lh = cy - ly0 + PAD - 8
        bands.insert(0, f'<rect x="0" y="{ly0}" width="{width}" height="{lh:.1f}" rx="10" fill="{T["band"]}"/>')
        fg.append(text(20, ly0 + lh / 2 + 5, layer["name"], 14, T["ink"], 600))
        fg.append(f'<line x1="{LBL}" y1="{ly0 + 14}" x2="{LBL}" y2="{ly0 + lh - 14:.1f}" stroke="{T["line"]}"/>')
        y = ly0 + lh + 10
    parts = bands + fg
    h = y + (34 if spec.get("legend") else 0)
    if spec.get("legend"):
        lx = 0
        for item in spec["legend"]:
            if item[0] == "box":
                dashed = item[1] == "ee"
                parts.append(f'<rect x="{lx}" y="{y + 8}" width="22" height="14" rx="3" fill="{T["accent_bg"] if item[1] == "focus" else T["paper"]}" '
                             f'stroke="{T["accent"] if item[1] == "focus" else T["line"]}"' + (' stroke-dasharray="4 3"' if dashed else "") + "/>")
                parts.append(text(lx + 30, y + 19.5, item[2], 12, T["muted"]))
                lx += 30 + tw(item[2], 12) + 26
            else:
                s2, pw = tag(lx, y + 7, item[1], "warn")
                parts.append(s2)
                parts.append(text(lx + pw + 8, y + 19.5, item[2], 12, T["muted"]))
                lx += pw + 8 + tw(item[2], 12) + 26
    return (f'<svg viewBox="0 0 {width} {h:.0f}" width="{width}" height="{h:.0f}" role="img" aria-label="{esc(spec["title"])}" '
            f'xmlns="http://www.w3.org/2000/svg" style="max-width:100%;height:auto">'
            '<rect x="0" y="0" width="100%" height="100%" fill="#FFFFFF"/>' + "\n".join(parts) + "</svg>")


def chips(x, y, items, maxw, kind="plain"):
    """flow-wrap small chips; returns (svg, height)"""
    out, cx, cy = [], x, y
    for it in items:
        w = tw(it, 12) + 18
        if cx + w > x + maxw and cx > x:
            cx, cy = x, cy + 30
        fill, stroke, color = ((T["accent_bg"], T["accent"], T["accent"]) if kind == "accent"
                               else (T["paper"], T["line"], T["ink"]))
        out.append(f'<rect x="{cx:.1f}" y="{cy:.1f}" width="{w:.1f}" height="24" rx="12" fill="{fill}" stroke="{stroke}"/>'
                   + text(cx + w / 2, cy + 16.5, it, 12, color, 400, "middle"))
        cx += w + 8
    return "\n".join(out), cy - y + 24


def corridor(spec, width=1040):
    """spec = {title, columns:[4 titles], rows:[{role:[...], scene, desc, caps:[...], ext:[...]}]}"""
    C = [(0, 140), (152, 300), (472, 352), (836, 204)]  # x, width per column
    parts = []
    for (x, w), t in zip(C, spec["columns"]):
        parts.append(text(x + 4, 18, t, 12.5, T["muted"], 600))
    y = 30
    for i, r in enumerate(spec["rows"]):
        _, h1 = chips(0, 0, r["role"], C[0][1] - 16)
        _, h3 = chips(0, 0, r["caps"], C[2][1] - 24, "accent")
        _, h4 = chips(0, 0, r["ext"], C[3][1] - 20)
        h = max(h1, h3, h4, 44) + 28
        s1, _ = chips(C[0][0] + 8, y + (h - h1) / 2, r["role"], C[0][1] - 16)
        s3, _ = chips(C[2][0] + 12, y + (h - h3) / 2, r["caps"], C[2][1] - 24, "accent")
        s4, _ = chips(C[3][0] + 12, y + (h - h4) / 2, r["ext"], C[3][1] - 20)
        if i % 2 == 0:
            parts.append(f'<rect x="0" y="{y}" width="{width}" height="{h:.0f}" rx="8" fill="{T["band"]}"/>')
        parts.append(f'<rect x="{C[1][0]}" y="{y + 10}" width="{C[1][1]}" height="{h - 20:.0f}" rx="6" fill="{T["paper"]}" stroke="{T["line"]}"/>')
        parts.append(text(C[1][0] + 12, y + h / 2 - 3, f'{i + 1}. {r["scene"]}', 13.5, T["ink"], 600))
        parts.append(text(C[1][0] + 12, y + h / 2 + 15, r["desc"], 11.5, T["muted"]))
        for xa in (C[1][0] - 4, C[2][0] - 2, C[3][0] - 2):
            my = y + h / 2
            parts.append(f'<path d="M{xa - 6:.0f} {my - 4:.0f} L{xa:.0f} {my:.0f} L{xa - 6:.0f} {my + 4:.0f}" fill="none" stroke="{T["muted"]}" stroke-width="1.4"/>')
        parts += [s1, s3, s4]
        y += h + 6
    return (f'<svg viewBox="0 0 {width} {y:.0f}" width="{width}" height="{y:.0f}" role="img" aria-label="{esc(spec["title"])}" '
            f'xmlns="http://www.w3.org/2000/svg" style="max-width:100%;height:auto">'
            '<rect x="0" y="0" width="100%" height="100%" fill="#FFFFFF"/>' + "\n".join(parts) + "</svg>")


def set_accent(hexv):
    """换品牌色只改这一处：浅底色按 10% 浓度自动推出"""
    h = hexv.lstrip("#")
    r, g, b = (int(h[k:k + 2], 16) for k in (0, 2, 4))
    T["accent"] = "#" + h.upper()
    T["accent_bg"] = "#%02X%02X%02X" % tuple(round(255 - (255 - c) * 0.10) for c in (r, g, b))


def main():
    import json
    import sys
    args = sys.argv[1:]
    usage = "用法: python3 diagrams.py <layered|corridor> spec.json out.svg [--accent '#RRGGBB']"
    if "--accent" in args:
        i = args.index("--accent")
        val = args[i + 1].lstrip("#") if i + 1 < len(args) else ""
        if not re.fullmatch(r"[0-9A-Fa-f]{6}", val):
            sys.exit("--accent 需要 6 位十六进制色值，如 '#3B51D4'（记得加引号）\n" + usage)
        set_accent(val)
        del args[i:i + 2]
    if len(args) != 3 or args[0] not in ("layered", "corridor"):
        sys.exit(usage)
    kind, src, dst = args
    try:
        with open(src, encoding="utf-8") as f:
            spec = json.load(f)
    except FileNotFoundError:
        sys.exit(f"找不到数据文件 {src}")
    except json.JSONDecodeError as e:
        sys.exit(f"{src} 不是合法 JSON（第 {e.lineno} 行第 {e.colno} 列：{e.msg}）；注意不能带注释和结尾逗号")
    try:
        svg = {"layered": layered, "corridor": corridor}[kind](spec)
    except (KeyError, TypeError) as e:
        sys.exit(f"{src} 结构不对（{type(e).__name__}: {e}）；对照本 skill 的 assets/examples/{kind}.example.json 修改")
    with open(dst, "w", encoding="utf-8") as f:
        f.write(svg)
    print(dst)


if __name__ == "__main__":
    main()
