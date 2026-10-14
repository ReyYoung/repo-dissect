"""repo-dissect 模板出图：JSON 数据 -> 确定性 SVG（只用 Python 标准库，Python 3.8+）。

layered(spec)   -> 分层架构 / 功能架构图（无连线的分层方块图）
corridor(spec)  -> 业务全景图（按场景成行的"场景走廊"，无交叉连线）

用法: python3 diagrams.py <layered|corridor> spec.json out.svg [--accent '#RRGGBB']
     （色值要加引号，否则 shell 会把 # 后面当注释）
     python3 diagrams.py check <spec.json|图.svg> ...   只做自查，不出图

出图前先按规模和字数上限自查（层数、每层模块数、行数、文字是否超出方框），出图后再检查每段文字是否超出画布；
有问题时列出来、不写文件、退出码 1。看不了图的环境（没有浏览器）就靠这一步兜底。
沙箱拒绝带变量的路径时，把路径展开成绝对路径再调用。
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
FONT = '-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei UI","Microsoft YaHei","Noto Sans CJK SC",sans-serif'


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


# ---- 自查 ------------------------------------------------------------------
LIMITS = {"layers": 6, "mods_per_layer": 10, "rows": 8, "mod_name": 8, "sub": 16, "desc": 20}


def nchars(s):
    """按汉字计的长度：中文 1，西文 0.5"""
    return sum(1 if ord(c) > 0x2E80 else 0.5 for c in s if not c.isspace())


def validate(kind, spec, width=1040):
    """返回 (errors, warnings)。errors 会让出图失败；warnings 只提示"""
    err, warn = [], []
    if not isinstance(spec, dict):
        return ["数据不是 JSON 对象"], warn
    if not spec.get("title"):
        err.append("缺少 title（一句话结论，也用作无障碍标签）")
    if kind == "layered":
        layers = spec.get("layers") or []
        if not layers:
            err.append("layers 为空")
        if len(layers) > LIMITS["layers"]:
            err.append(f"共 {len(layers)} 层，超过上限 {LIMITS['layers']}：合并相近的层，或拆成两张图")
        LBL, PAD, GAP, BW_MIN = 112, 16, 12, 150
        inner = width - LBL - PAD * 2
        cols = max(1, int((inner + GAP) // (BW_MIN + GAP)))
        bw = (inner - GAP * (cols - 1)) / cols
        for L in layers:
            ln = L.get("name", "")
            if tw(ln, 14) > LBL - 28:
                err.append(f"层名「{ln}」太长，左侧标签栏放不下（约 6 个汉字以内）")
            # 虚线分组（企业版等）单独成框，不计入本层主体的模块数
            main = [m for g in L.get("groups", []) if not g.get("dashed") for m in g.get("modules", [])]
            if len(main) > LIMITS["mods_per_layer"]:
                err.append(f"「{ln}」层有 {len(main)} 个模块，超过上限 {LIMITS['mods_per_layer']}：合并相近模块或拆层")
            for g in L.get("groups", []):
                if g.get("dashed") and len(g.get("modules", [])) > LIMITS["mods_per_layer"]:
                    err.append(f"「{ln}」层的分组「{g.get('title', '')}」有 {len(g['modules'])} 个模块，超过上限")
            for g in L.get("groups", []):
                if g.get("title") and tw(g["title"], 11.5) > inner:
                    err.append(f"分组标题「{g['title']}」超出画布")
                for m in g.get("modules", []):
                    name, sub = m.get("name", ""), m.get("sub") or ""
                    if not name:
                        err.append(f"「{ln}」层有模块缺少 name")
                    if tw(name, 13) > bw - 4:
                        err.append(f"模块名「{name}」超出方框（宽 {bw:.0f}px），请缩短")
                    elif nchars(name) > LIMITS["mod_name"]:
                        warn.append(f"模块名「{name}」超过 {LIMITS['mod_name']} 个字，建议缩短")
                    if sub and tw(sub, 11) > bw - 4:
                        err.append(f"副标题「{sub}」超出方框，请缩短（建议 ≤ {LIMITS['sub']} 个字符）")
                    pill = m.get("tag") or STATUS.get(m.get("status"), STATUS[None])[2]
                    if pill and tw(pill, 10) + 16 > bw:
                        err.append(f"标签「{pill}」比方框还宽")
    elif kind == "corridor":
        rows = spec.get("rows") or []
        if len(spec.get("columns") or []) != 4:
            err.append("columns 必须正好 4 个列标题")
        if not rows:
            err.append("rows 为空")
        if len(rows) > LIMITS["rows"]:
            err.append(f"共 {len(rows)} 行场景，超过上限 {LIMITS['rows']}：合并相近场景或拆图")
        C = [(0, 140), (152, 300), (472, 352), (836, 204)]
        for i, r in enumerate(rows):
            scene, desc = f"{i + 1}. {r.get('scene', '')}", r.get("desc", "")
            if tw(scene, 13.5) > C[1][1] - 24:
                err.append(f"场景名「{r.get('scene', '')}」超出方框，请缩短")
            if tw(desc, 11.5) > C[1][1] - 24:
                err.append(f"场景说明「{desc}」超出方框，请缩短到 {LIMITS['desc']} 字以内")
            elif nchars(desc) > LIMITS["desc"]:
                warn.append(f"场景说明「{desc}」超过 {LIMITS['desc']} 字")
            for key, col, pad in (("role", 0, 16), ("caps", 2, 24), ("ext", 3, 20)):
                for it in r.get(key, []):
                    if tw(it, 12) + 18 > C[col][1] - pad:
                        err.append(f"「{it}」（{key}）比所在列还宽，请缩短")
    return err, warn


TEXT_RE = re.compile(r'<text x="([\d.-]+)" y="([\d.-]+)" font-size="([\d.]+)"[^>]*?text-anchor="(\w+)"[^>]*>([^<]*)</text>')


def check_svg(svg):
    """出图后检查：每段文字按字号估算宽度，看是否超出 viewBox"""
    m = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    if not m:
        return ["找不到 viewBox，无法检查"]
    W, H = float(m.group(1)), float(m.group(2))
    bad = []
    for x, y, size, anchor, body in TEXT_RE.findall(svg):
        x, y, size, t = float(x), float(y), float(size), html.unescape(body)
        w = tw(t, size)
        left = x - (w / 2 if anchor == "middle" else w if anchor == "end" else 0)
        if left < -1 or left + w > W + 1 or y > H + 1 or y - size < -1:
            bad.append(f"文字「{t}」超出画布（{left:.0f}–{left + w:.0f}px，画布宽 {W:.0f}px）")
    return bad


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
    usage = ("用法: python3 diagrams.py <layered|corridor> spec.json out.svg [--accent '#RRGGBB']\n"
             "     python3 diagrams.py check <spec.json|图.svg> ...")
    if args and args[0] == "check":
        return check_main(args[1:], usage)
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
        err, warn = validate(kind, spec)
    except (KeyError, TypeError, AttributeError) as e:
        sys.exit(f"{src} 结构不对（{type(e).__name__}: {e}）；对照本 skill 的 assets/examples/{kind}.example.json 修改")
    for w in warn:
        print("提示:", w)
    if err:
        print(f"{src} 有 {len(err)} 处超出规模或字数上限，未出图：", file=sys.stderr)
        for e in err:
            print("  -", e, file=sys.stderr)
        sys.exit(1)
    try:
        svg = {"layered": layered, "corridor": corridor}[kind](spec)
    except (KeyError, TypeError, AttributeError) as e:
        sys.exit(f"{src} 结构不对（{type(e).__name__}: {e}）；对照本 skill 的 assets/examples/{kind}.example.json 修改")
    over = check_svg(svg)
    if over:
        print(f"出图后自查发现 {len(over)} 处文字超出画布，未写文件：", file=sys.stderr)
        for e in over:
            print("  -", e, file=sys.stderr)
        sys.exit(1)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(svg)
    print(dst + "（已自查：规模、字数、文字是否超出画布）")


def check_main(paths, usage):
    import json
    import sys
    if not paths:
        sys.exit(usage)
    bad = 0
    for pth in paths:
        try:
            with open(pth, encoding="utf-8") as f:
                data = f.read()
        except OSError as e:
            print(f"{pth}: 读不了（{e}）")
            bad += 1
            continue
        if pth.lower().endswith(".svg"):
            err, warn = check_svg(data), []
        else:
            try:
                spec = json.loads(data)
            except json.JSONDecodeError as e:
                print(f"{pth}: 不是合法 JSON（第 {e.lineno} 行）")
                bad += 1
                continue
            kind = "layered" if isinstance(spec, dict) and "layers" in spec else "corridor"
            try:
                err, warn = validate(kind, spec)
            except (KeyError, TypeError, AttributeError) as e:
                err, warn = [f"结构不对（{type(e).__name__}: {e}），对照 assets/examples/{kind}.example.json 修改"], []
        print(f"{pth}: " + ("通过" if not err else f"{len(err)} 处问题"))
        for e in err:
            print("  -", e)
        for w in warn:
            print("  提示:", w)
        bad += len(err)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
