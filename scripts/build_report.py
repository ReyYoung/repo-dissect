"""repo-dissect 报告页生成：report.json + 各层 Markdown -> 单文件 report.html

用法: python3 build_report.py <OUT目录> [--mermaid auto|static|inline]
      读取 <OUT>/report.json，写出 <OUT>/report.html（单文件，离线可看）
依赖: 只需 Python 3.8+ 标准库（内置 Markdown 转换器）。
Mermaid 图（流程、时序、状态、ER）两种离线方式：
  static  用 Playwright 预渲染成静态 SVG，报告体积小，并会报出 Mermaid 语法错误（需要 Python playwright）
  inline  把随附的 assets/vendor/mermaid.min.js（约 2.7 MB）内联进报告，打开时渲染
  auto    默认：能用 Playwright 就 static，否则 inline
"""
import html
import base64
import json
import re
import sys
from pathlib import Path

_args = sys.argv[1:]
MODE = "auto"
if "--mermaid" in _args:
    _i = _args.index("--mermaid")
    MODE = _args[_i + 1] if _i + 1 < len(_args) else ""
    del _args[_i:_i + 2]
if len(_args) != 1 or MODE not in ("auto", "static", "inline"):
    sys.exit("用法: python3 build_report.py <OUT目录> [--mermaid auto|static|inline]")
OUT = Path(_args[0]).resolve()
MERMAID_JS = Path(__file__).resolve().parent.parent / "assets" / "vendor" / "mermaid.min.js"
MERMAIDS = []  # 全报告的 Mermaid 源码，按出现顺序编号
if not (OUT / "report.json").is_file():
    sys.exit(f"找不到 {OUT / 'report.json'}；格式参考本 skill 的 assets/examples/report.example.json")
CFG = json.loads((OUT / "report.json").read_text(encoding="utf-8"))
for key in ("title", "verdict", "sections"):
    if key not in CFG:
        sys.exit(f"report.json 缺少字段 {key}；参考 assets/examples/report.example.json")
E = html.escape


# ---- 内置 Markdown 转换器（覆盖拆解文档用到的语法：标题、段落、嵌套列表、表格、代码块、引用、链接、图片）----
_LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_BLOCK_START = re.compile(r"^(#{1,6}\s|```|>|\|)")


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _inline(s):
    codes = []

    def keep_code(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"
    s = re.sub(r"`([^`]+)`", keep_code, s)
    s = E(s, quote=False)
    s = re.sub(r"&lt;br\s*/?&gt;", "<br>", s)
    s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", r'<img alt="\1" src="\2">', s)
    s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*(?![\s*])(.+?)(?<![\s*])\*(?![*\w])", r"<em>\1</em>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: "<code>" + E(codes[int(m.group(1))], quote=False) + "</code>", s)


def _cells(row):
    row = row.strip()
    row = row[1:] if row.startswith("|") else row
    row = row[:-1] if row.endswith("|") and not row.endswith("\\|") else row
    cells, cur, in_code = [], "", False
    i = 0
    while i < len(row):
        ch = row[i]
        if ch == "\\" and i + 1 < len(row) and row[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    cells.append(cur.strip())
    return cells


def _list(lines, i):
    m = _LIST.match(lines[i])
    base, ordered = _indent(lines[i]), m.group(2)[0].isdigit()
    items = []
    while i < len(lines):
        line = lines[i]
        m = _LIST.match(line)
        if m and _indent(line) == base and m.group(2)[0].isdigit() == ordered:
            items.append([m.group(3)])
        elif not line.strip():
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            nxt = lines[j] if j < len(lines) else ""
            nm = _LIST.match(nxt)
            if j < len(lines) and (_indent(nxt) > base or (nm and _indent(nxt) == base and nm.group(2)[0].isdigit() == ordered)):
                i = j
                continue
            break
        elif _indent(line) > base or not (_BLOCK_START.match(line.lstrip()) or m):
            items[-1].append(line)
        else:
            break
        i += 1
    out = []
    for it in items:
        rest = it[1:]
        if any(_LIST.match(x) or x.lstrip().startswith(("```", "|", ">")) for x in rest):
            pad = min(_indent(x) for x in rest if x.strip())
            out.append(f"<li>{_inline(it[0])}\n{_blocks([x[pad:] for x in rest])}</li>")
        else:
            out.append("<li>" + _inline(" ".join([it[0]] + [x.strip() for x in rest])) + "</li>")
    tagname = "ol" if ordered else "ul"
    return f"<{tagname}>\n" + "\n".join(out) + f"\n</{tagname}>", i


def _blocks(lines):
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        st = line.strip()
        if not st:
            i += 1
        elif st.startswith("```"):
            lang = st[3:].strip()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            cls = f' class="language-{E(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>" + E("\n".join(lines[i + 1:j]), quote=False) + "\n</code></pre>")
            i = j + 1
        elif re.match(r"^#{1,6}\s", st):
            n = len(st) - len(st.lstrip("#"))
            out.append(f"<h{n}>{_inline(st[n:].strip().rstrip('#').strip())}</h{n}>")
            i += 1
        elif re.match(r"^(-{3,}|\*{3,}|_{3,})$", st):
            out.append("<hr>")
            i += 1
        elif st.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-{2,}", lines[i + 1].strip()):
            head = _cells(st)
            rows, j = [], i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append(_cells(lines[j]))
                j += 1
            th = "".join(f"<th>{_inline(c)}</th>" for c in head)
            trs = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in (r + [""] * len(head))[:len(head)]) + "</tr>\n" for r in rows)
            out.append(f"<table>\n<thead>\n<tr>{th}</tr>\n</thead>\n<tbody>\n{trs}</tbody>\n</table>")
            i = j
        elif st.startswith(">"):
            j, q = i, []
            while j < len(lines) and lines[j].strip().startswith(">"):
                q.append(re.sub(r"^\s*>\s?", "", lines[j]))
                j += 1
            out.append("<blockquote>\n" + _blocks(q) + "\n</blockquote>")
            i = j
        elif _LIST.match(line):
            h, i = _list(lines, i)
            out.append(h)
        else:
            j, para = i, []
            while j < len(lines) and lines[j].strip() and not _BLOCK_START.match(lines[j].strip()) \
                    and not _LIST.match(lines[j]) and not re.match(r"^(-{3,}|\*{3,})$", lines[j].strip()):
                para.append(lines[j].strip())
                j += 1
            if not para:  # 以 | 开头但不是表格的行
                para, j = [st], i + 1
            out.append("<p>" + _inline("\n".join(para)) + "</p>")
            i = j
    return "\n".join(out)


def md_to_html(text):
    return _blocks(text.split("\n"))


def _tint(hexv, k):
    """把强调色和白色按比例混合，得到浅底色（k=0.1 即 10% 浓度）"""
    h = hexv.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02X%02X%02X" % tuple(round(255 - (255 - c) * k) for c in (r, g, b))


def _shade(hexv, k):
    h = hexv.lstrip("#")
    return "#%02X%02X%02X" % tuple(round(int(h[i:i + 2], 16) * k) for i in (0, 2, 4))


ACCENT = "#" + str(CFG.get("accent", "#3B51D4")).lstrip("#").upper()  # 强调色，可在 report.json 里用 "accent" 覆盖
if not re.fullmatch(r"#[0-9A-Fa-f]{6}", ACCENT):
    sys.exit(f"report.json 的 accent 必须是 #RRGGBB 格式，现在是 {CFG.get('accent')!r}")
if ACCENT == "#3B51D4":  # 默认色用精确调好的配套色
    P50, P100, P700 = "#EEF1FE", "#DBE2FD", "#2D3FAE"
else:
    P50, P100, P700 = _tint(ACCENT, 0.10), _tint(ACCENT, 0.18), _shade(ACCENT, 0.77)

TONE = {  # 语义色只表状态，且必须配文字
    "good": ("#E2F3E8", "#1F7A41"), "info": ("#E0F5F9", "#087F95"), "warn": ("#FCF0DC", "#A25E00"),
    "bad": ("#FBE9E9", "#C03636"), "default": ("#ECEEF4", "#59627A"), "brand": (P50, P700),
}
VERDICT_TONE = {"推荐": "good", "有条件推荐": "warn", "不推荐": "bad"}
CELL_TAGS = {  # 表格里的结论词 -> 状态标签
    "满足": "good", "部分满足": "info", "需二次开发": "warn", "仅企业版满足": "warn", "不满足": "bad",
    "推荐": "good", "有条件推荐": "warn", "不推荐": "bad",
}
MARKS = {"✅": ("事实", "good"), "🔍": ("推断", "info"), "❓": ("待确认", "warn")}


def tag(text, tone="default", small=False):
    bg, fg = TONE[tone]
    return f'<span class="tag{" sm" if small else ""}" style="background:{bg};color:{fg}">{E(text)}</span>'


def _retag(body):
    """结论词、✅🔍❓ 转成标签；跳过代码块和行内代码"""
    parts = re.split(r"(<pre>.*?</pre>|<code[^>]*>.*?</code>)", body, flags=re.S)
    for k in range(0, len(parts), 2):
        x = parts[k]
        for word, tone in CELL_TAGS.items():  # **满足** 或单元格里只有结论词 -> 标签
            x = x.replace(f"<strong>{word}</strong>", tag(word, tone)).replace(f"<td>{word}</td>", f"<td>{tag(word, tone)}</td>")
        for mark, (lbl, tone) in MARKS.items():
            x = x.replace(mark, tag(lbl, tone, small=True))
        parts[k] = x
    return "".join(parts)


def convert(md_text, sec_id, label):
    blocks = []

    def keep(h):
        blocks.append(h)
        return f"\n\nBLOCK{len(blocks) - 1}END\n\n"

    def mermaid(m):
        before = md_text[: m.start()]
        heads = re.findall(r"^#+\s*(.+)$", before, flags=re.M)
        name = re.sub(r"[`*\\/:]", "", heads[-1]).strip() if heads else "diagram"
        MERMAIDS.append(m.group(1))
        return keep(f'<figure class="diagram" data-name="{E(name)}">\x00MERMAID{len(MERMAIDS) - 1}\x00</figure>')

    def svgfig(m):
        alt, path, cap = m.group(1), m.group(2), m.group(3) or m.group(1)
        if not (OUT / path).is_file():
            print(f"警告：找不到图 {path}，保留为普通图片引用", file=sys.stderr)
            return m.group(0)
        svg = (OUT / path).read_text(encoding="utf-8")
        name = re.sub(r"^图 ?\d+[：:]", "", alt).strip()[:24] or path
        cap_html = re.sub(r"`([^`]+)`", r"<code>\1</code>", E(cap))
        return keep(f'<figure class="diagram tpl" data-name="{E(name)}"><div class="fig-scroll">{svg}</div>'
                    f"<figcaption>{cap_html}</figcaption></figure>")

    md_text = md_text.replace("\r\n", "\n")
    text = re.sub(r"```mermaid[ \t]*\n(.*?)```", mermaid, md_text, flags=re.S)
    text = re.sub(r"!\[([^\]]*)\]\((img/[^)]+\.svg)\)[ \t]*\n(?:(?:[ \t]*\n)?\*(.+?)\*[ \t]*\n)?", svgfig, text + "\n")
    text = re.sub(r"^(#{1,5}) ", lambda m: "#" + m.group(1) + " ", text, flags=re.M)  # 文件 H1 -> 页面 H2
    body = md_to_html(text)
    if "<h2>" not in body:  # 文档没有以 "# 标题" 开头时，用目录名补一个章节标题
        body = f"<h2>{E(label)}</h2>\n" + body
    body = _retag(body)
    for i, b in enumerate(blocks):
        body = body.replace(f"<p>BLOCK{i}END</p>", b)
    body = body.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")
    body = re.sub(r"<blockquote>", '<div class="alert info"><span class="dot">i</span><div>', body)
    body = body.replace("</blockquote>", "</div></div>")
    body = re.sub(r'<a href="(https?://[^"]+)"', r'<a href="\1" target="_blank" rel="noopener"', body)
    # 标题加锚点
    n = [0]

    def hid(m):
        n[0] += 1
        return f'<{m.group(1)} id="{sec_id}-{n[0]}">'
    body = re.sub(r"<(h[234])>", hid, body)
    # "附录：完整功能清单" 之类的长附录折叠起来（文件里的 ## 或 ### 标题）
    for lv, stop in (("4", "234"), ("3", "23")):
        body = re.sub(rf'<h{lv} id="[^"]+">(附录[^<]*)</h{lv}>(.*?)(?=<h[{stop}] |$)',
                      lambda m: f'<details class="collapse"><summary>{m.group(1)}</summary>{m.group(2)}</details>',
                      body, flags=re.S)
    return body


secs, nav = [], []
for i, s in enumerate(CFG["sections"]):
    fname, label = s[0], s[1]
    appendix = len(s) > 2 and s[2] == "appendix"
    sid = f"s{i}"
    if not (OUT / fname).is_file():
        sys.exit(f"report.json 的 sections 里列了 {fname}，但 {OUT} 下没有这个文件")
    body = convert((OUT / fname).read_text(encoding="utf-8"), sid, label)
    if appendix:
        first_h2 = re.search(r"<h2[^>]*>(.*?)</h2>", body)
        title = first_h2.group(1) if first_h2 else label
        body = re.sub(r"<h2[^>]*>.*?</h2>", "", body, count=1)
        secs.append(f'<section class="sec" id="{sid}" data-label="{E(label)}"><details class="collapse big">'
                    f'<summary><span class="secno">{i + 1:02d}</span>{title}</summary>{body}</details></section>')
    else:
        body = re.sub(r"<h2([^>]*)>", rf'<h2\1><span class="secno">{i + 1:02d}</span>', body, count=1)
        secs.append(f'<section class="sec" id="{sid}" data-label="{E(label)}">{body}</section>')
    nav.append(f'<a href="#{sid}" data-sec="{sid}"><span class="ico"></span>{E(label)}</a>')

v = CFG["verdict"]
vt = VERDICT_TONE.get(v["level"], "default")
crumbs = ' <span class="sep">/</span> '.join(E(c) for c in CFG.get("crumbs", []))
meta = "".join(f"<span class=\"dk\">{E(k)}</span><span class=\"dv\">{E(val)}</span>" for k, val in CFG.get("meta", []))
stats = ""
for item in CFG.get("stats", []):  # [数值, 标签, 补充说明?]；写成循环以兼容 Python 3.8+
    val, lbl = item[0], item[1]
    note = f'<div class="sn">{E(item[2])}</div>' if len(item) > 2 and item[2] else ""
    stats += f'<div class="stat"><div class="sl">{E(lbl)}</div><div class="sv">{E(val)}</div>{note}</div>'
notice = ""
if CFG.get("notice"):
    nt = CFG["notice"]
    notice = (f'<div class="alert {nt.get("tone", "warn")}"><span class="dot">!</span><div>{E(nt["text"])}</div></div>')

CSS = """
:root{--p50:__P50__;--p100:__P100__;--p600:__P600__;--p700:__P700__;--bg:#F6F7FA;--line:#ECEEF4;--card:#E3E6EE;
--ctl:#8694B6;--weak:#697189;--sub:#59627A;--ink:#181D2B;--ink2:#3C4356;--warn:#A25E00}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.75 -apple-system,"Segoe UI","PingFang SC","Noto Sans SC","Source Han Sans SC","Microsoft YaHei",sans-serif;font-variant-numeric:tabular-nums}
a{color:var(--p600);text-decoration:none}a:hover{text-decoration:underline}
.layout{display:grid;grid-template-columns:232px minmax(0,1fr) 200px;min-height:100vh}
/* 侧边导航：宽 232 · 白底右描边 · 当前项强调色浅底 */
.side{position:sticky;top:0;height:100vh;overflow:auto;background:#fff;border-right:1px solid var(--card);padding:14px 10px}
.brand{display:flex;gap:10px;align-items:center;padding:6px 10px 16px}
.brand .mk{width:30px;height:30px;border-radius:8px;background:var(--p600);color:#fff;font-weight:700;font-size:13px;display:flex;align-items:center;justify-content:center}
.brand img.logo{width:34px;height:34px;background:none;border-radius:0;object-fit:contain;flex:none}
.brand b{display:block;font-size:13.5px}.brand small{display:block;font-size:11px;color:var(--weak);font-weight:600;letter-spacing:.04em}
.side nav{display:flex;flex-direction:column;gap:2px}
.side nav a{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:7px;color:var(--sub);font-size:13px;text-decoration:none}
.side nav a:hover{background:var(--bg)}
.side nav a .ico{width:8px;height:8px;border-radius:2.5px;background:var(--weak);flex:none}
.side nav a.on{background:var(--p50);color:var(--p700);font-weight:600}.side nav a.on .ico{background:var(--p600)}
.side .grp{font-size:11px;color:var(--weak);font-weight:600;padding:14px 12px 6px}
.main{padding:24px 40px 80px;min-width:0}
.crumb{font-size:12px;color:var(--weak);margin-bottom:10px}.crumb .sep{margin:0 6px;color:var(--ctl)}
.head{display:flex;align-items:flex-start;gap:16px;margin-bottom:18px}
h1{font-size:26px;font-weight:700;line-height:1.35;margin:0}
.aux{font-size:12px;color:var(--weak);margin-top:4px}
.btn{font:500 12px inherit;font-family:inherit;height:30px;padding:0 12px;border-radius:6px;border:1px solid var(--ctl);background:#fff;color:var(--ink2);cursor:pointer;white-space:nowrap}
.btn:hover{border-color:var(--p600);color:var(--p600)}
.head .btn{margin-left:auto}
.card{background:#fff;border:1px solid var(--card);border-radius:12px;padding:24px 28px;margin-bottom:16px}
.verdict{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:28px}
.verdict h2{font-size:20px;line-height:1.4;margin:10px 0 8px}
.verdict ol{margin:6px 0 0;padding-left:20px;color:var(--ink2)}.verdict li{margin:4px 0}
.desc{display:grid;grid-template-columns:auto 1fr;border:1px solid var(--card);border-radius:8px;overflow:hidden;font-size:12.5px;align-self:start}
.desc .dk{padding:8px 12px;background:var(--bg);color:var(--sub);border-bottom:1px solid var(--line);white-space:nowrap}
.desc .dv{padding:8px 12px;border-bottom:1px solid var(--line);word-break:break-all}
.desc .dk:nth-last-child(2),.desc .dv:last-child{border-bottom:none}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:16px}
.stat{background:#fff;border:1px solid var(--card);border-radius:12px;padding:14px 18px}
.stat .sl{font-size:11px;color:var(--weak)}.stat .sv{font-size:24px;font-weight:700;line-height:1.35;margin-top:2px}
.stat .sn{font-size:11.5px;color:var(--sub);margin-top:2px}
.tag{display:inline-block;font-size:11px;font-weight:600;padding:2px 9px;border-radius:4px;white-space:nowrap;line-height:1.6;vertical-align:1px}
.tag.sm{font-size:10px;padding:0 6px;margin:0 2px}
.alert{display:flex;gap:10px;align-items:flex-start;border-radius:8px;padding:10px 14px;font-size:12.5px;margin:12px 0}
.alert .dot{width:16px;height:16px;border-radius:99px;color:#fff;font-size:11px;font-weight:700;display:inline-flex;align-items:center;justify-content:center;flex:none;margin-top:3px}
.alert.warn{background:#FCF0DC;border:1px solid #F4D9AE;color:#8A5200}.alert.warn .dot{background:#D17A00}
.alert.info{background:#F2FAFC;border:1px solid #C5E8EF;color:#3C4356}.alert.info .dot{background:#087F95}
.alert p{margin:2px 0}
.sec{background:#fff;border:1px solid var(--card);border-radius:12px;padding:8px 32px 26px;margin-bottom:16px;scroll-margin-top:16px}
.sec h2{font-size:20px;font-weight:700;line-height:1.4;margin:22px 0 12px;display:flex;align-items:baseline;gap:10px}
.secno{font:700 11px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--weak)}
.sec h3{font-size:16px;font-weight:600;line-height:1.5;margin:26px 0 8px;scroll-margin-top:16px}
.sec h4{font-size:14px;font-weight:600;margin:18px 0 6px}
.sec p,.sec li{color:var(--ink2);overflow-wrap:anywhere}
.sec strong{color:var(--ink)}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;background:var(--line);color:var(--ink2);padding:1px 5px;border-radius:4px;word-break:break-word}
pre{background:var(--bg);border:1px solid var(--card);border-radius:8px;padding:12px 14px;overflow-x:auto}pre code{background:none;padding:0}
.table-wrap{border:1px solid var(--card);border-radius:10px;overflow-x:auto;margin:12px 0 18px}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:640px}
th{background:var(--bg);font-size:12px;font-weight:600;color:var(--sub);text-align:left;padding:10px 14px;white-space:nowrap}
td{padding:10px 14px;border-top:1px solid var(--line);vertical-align:top;color:var(--ink2)}
tr:hover td{background:var(--bg)}
figure.diagram{margin:14px 0 20px;border:1px solid var(--card);border-radius:10px;padding:16px;background:#fff}
.fig-scroll{overflow-x:auto}.fig-scroll svg{min-width:760px;display:block}
.mermaid{overflow-x:auto;text-align:center}.mermaid:not([data-processed]){white-space:pre;font:12px ui-monospace,monospace;color:var(--weak)}
.mermaid svg{max-width:100%;height:auto}
.mermaid-svg{overflow-x:auto;text-align:center}.mermaid-svg svg{max-width:none;height:auto}
.mermaid[data-processed] svg{max-width:none!important;height:auto}
figcaption{font-size:12px;color:var(--weak);margin-top:10px}
.figbar{display:flex;gap:8px;margin-top:10px}.figbar .btn{height:26px;padding:0 10px}
details.collapse{border:1px solid var(--card);border-radius:8px;margin:14px 0;padding:0 16px}
details.collapse>summary{cursor:pointer;padding:10px 0;font-weight:600;font-size:13.5px;color:var(--ink);list-style:none}
details.collapse>summary::before{content:"▸";display:inline-block;width:16px;color:var(--weak);transition:transform .15s}
details.collapse[open]>summary::before{transform:rotate(90deg)}
details.collapse.big{border:none;margin:0;padding:0}details.collapse.big>summary{font-size:20px;padding:22px 0 12px;display:flex;gap:10px;align-items:baseline}
/* 锚点目录（长文档页） */
.anchor{position:sticky;top:0;height:100vh;overflow:auto;padding:28px 16px 28px 0;font-size:12.5px}
.anchor .t{font-size:12px;font-weight:600;color:var(--sub);margin-bottom:10px}
.anchor a{display:block;padding:5px 0 5px 14px;border-left:2px solid var(--line);color:var(--sub);text-decoration:none;line-height:1.5}
.anchor a.l4{padding-left:26px}.anchor a.on{border-left-color:var(--p600);color:var(--p600);font-weight:600}
footer{font-size:12px;color:var(--weak);margin-top:24px}
@media (max-width:1280px){.layout{grid-template-columns:232px minmax(0,1fr)}.anchor{display:none}}
@media (max-width:860px){.layout{display:block}.side{position:sticky;top:0;z-index:5;height:auto;padding:8px 12px;border-right:none;border-bottom:1px solid var(--card)}
.brand{display:none}.side .grp{display:none}.side nav{flex-direction:row;overflow-x:auto;gap:4px}.side nav a{white-space:nowrap;padding:6px 10px}
.main{padding:16px 16px 60px}.verdict{grid-template-columns:1fr}.sec{padding:4px 16px 18px}.card{padding:18px}.head .btn{display:none}}
@media print{.side,.anchor,.btn,.figbar{display:none}.layout{display:block}.main{padding:0}.sec,.card,.stat{break-inside:auto;border-color:#ddd}body{background:#fff}details.collapse{display:block}}
""".replace("__P50__", P50).replace("__P100__", P100).replace("__P600__", ACCENT).replace("__P700__", P700)

JS = r"""
<script type="module">
// 1) Mermaid：inline 模式下用内联的 mermaid.min.js 渲染；static 模式下已是静态 SVG
if (window.mermaid && document.querySelector('.mermaid')) {
  try {
    mermaid.initialize(MERMAID_CFG);
    await mermaid.run({ querySelector: '.mermaid' });
    document.querySelectorAll('.mermaid svg').forEach(s => { const w = parseFloat(s.style.maxWidth); if (w) { s.setAttribute('width', Math.round(w)); s.style.maxWidth = ''; } });
  } catch (e) { console.warn('Mermaid 渲染失败，以源码显示', e); }
}
// 2) 每张图下的下载按钮
document.querySelectorAll('figure.diagram').forEach((fig, i) => {
  const svgEl = () => fig.querySelector('svg');
  if (!svgEl()) return;
  const name = fig.dataset.name || `diagram-${i + 1}`;
  const save = (href, ext) => { const a = document.createElement('a'); a.download = `${name}.${ext}`; a.href = href; a.click(); };
  const size = () => { const vb = svgEl().viewBox.baseVal; const r = svgEl().getBoundingClientRect(); return vb && vb.width ? { w: vb.width, h: vb.height } : { w: r.width, h: r.height }; };
  const svgText = () => { const s = svgEl().cloneNode(true); const { w, h } = size(); s.setAttribute('width', w); s.setAttribute('height', h); s.removeAttribute('style'); return new XMLSerializer().serializeToString(s); };
  const bar = document.createElement('div'); bar.className = 'figbar';
  const mk = (t, fn) => { const b = document.createElement('button'); b.className = 'btn'; b.textContent = t; b.onclick = fn; bar.append(b); };
  mk('下载 SVG', () => save(URL.createObjectURL(new Blob([svgText()], { type: 'image/svg+xml' })), 'svg'));
  mk('下载 PNG', () => { const { w, h } = size(); const img = new Image(); img.onload = () => { const c = document.createElement('canvas'); c.width = w * 2; c.height = h * 2; const x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, c.width, c.height); x.drawImage(img, 0, 0, c.width, c.height); save(c.toDataURL('image/png'), 'png'); }; img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgText()); });
  fig.append(bar);
});
// 3) 侧边导航高亮 + 右侧锚点目录随当前章节切换
const secs = [...document.querySelectorAll('section.sec')];
const navs = Object.fromEntries([...document.querySelectorAll('.side nav a')].map(a => [a.dataset.sec, a]));
const anchor = document.querySelector('.anchor .list');
let cur = null;
const setSec = (sec) => {
  if (!sec || sec === cur) return; cur = sec;
  Object.values(navs).forEach(a => a.classList.toggle('on', a.dataset.sec === sec.id));
  if (!anchor) return;
  anchor.innerHTML = '';
  sec.querySelectorAll('h3[id], h4[id]').forEach(h => { if (h.closest('details:not([open])')) return; const a = document.createElement('a'); a.href = '#' + h.id; a.textContent = h.textContent; if (h.tagName === 'H4') a.className = 'l4'; anchor.append(a); });
};
const onScroll = () => {
  const y = window.scrollY + 120;
  if (y < secs[0].offsetTop) { cur = null; Object.values(navs).forEach(a => a.classList.toggle('on', a.dataset.sec === 'top')); if (anchor) anchor.innerHTML = ''; return; }
  let s = secs[0]; for (const x of secs) if (x.offsetTop <= y) s = x; setSec(s);
  if (!anchor) return;
  let on = null; anchor.querySelectorAll('a').forEach(a => { const h = document.getElementById(a.getAttribute('href').slice(1)); if (h && h.getBoundingClientRect().top < 140) on = a; });
  anchor.querySelectorAll('a').forEach(a => a.classList.toggle('on', a === on));
};
window.addEventListener('scroll', onScroll, { passive: true }); onScroll();
document.querySelector('[data-print]')?.addEventListener('click', () => { document.querySelectorAll('details').forEach(d => d.open = true); window.print(); });
</script>
"""

def data_uri(path):
    mime = {".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".webp": "image/webp", ".ico": "image/x-icon"}.get(path.suffix.lower())
    if not mime or not path.is_file():
        return None
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


# 左上角标识：report.json 的 "logo"（相对输出目录的图片路径）优先，否则用技能自带的 repo-dissect 标识；都没有就用文字方块
BRAND_DIR = Path(__file__).resolve().parent.parent / "assets" / "brand"
LOGO = data_uri(OUT / CFG["logo"]) if CFG.get("logo") else None
if CFG.get("logo") and not LOGO:
    print(f"提示：report.json 的 logo 文件 {CFG['logo']} 不存在或格式不支持（png/svg/jpg/webp），改用默认标识")
LOGO = LOGO or data_uri(BRAND_DIR / "repo-dissect-mark-96.png")
FAVICON = (data_uri(OUT / CFG["logo"]) if CFG.get("logo") else None) or data_uri(BRAND_DIR / "repo-dissect-mark-64.png")
MARK = f'<img class="mk logo" src="{LOGO}" alt="">' if LOGO else '<div class="mk">拆</div>'

page = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(CFG['title'])}</title>
{f'<link rel="icon" href="{FAVICON}">' if FAVICON else ''}<style>{CSS}</style></head>
<body><div class="layout">
<aside class="side"><div class="brand">{MARK}<div><b>{E(CFG.get('product', '开源项目拆解'))}</b><small>repo-dissect</small></div></div>
<div class="grp">报告目录</div><nav><a href="#top" data-sec="top"><span class="ico"></span>结论概览</a>{''.join(nav)}</nav></aside>
<main class="main"><div id="top"></div>
<div class="crumb">{crumbs}</div>
<div class="head"><div><h1>{E(CFG['title'])}</h1><div class="aux">{E(CFG.get('subtitle', ''))}</div></div>
<button class="btn" data-print>打印 / 导出 PDF</button></div>
<div class="card verdict"><div>{tag(v['level'], vt)}<h2>{E(v['summary'])}</h2>
<ol>{''.join(f'<li>{E(p)}</li>' for p in v.get('points', []))}</ol></div>
<div class="desc">{meta}</div></div>
<div class="stats">{stats}</div>
{notice}
{''.join(secs)}
<footer>{E(CFG.get('footer', ''))}</footer>
</main>
<aside class="anchor"><div class="t">本章目录</div><div class="list"></div></aside>
</div>{JS}</body></html>"""

# ---- Mermaid：预渲染成静态 SVG，或内联渲染库 ----
# 关闭 HTML 标签，否则导出 PNG 时画布会被浏览器判定为"被污染"而失败；
# 字体在这里统一设置（Mermaid 不认 themeVariables 里的 fontFamily）
MERMAID_CFG = '{"startOnLoad": false, "securityLevel": "strict", "htmlLabels": false, "flowchart": {"htmlLabels": false}, "fontFamily": "-apple-system, Segoe UI, PingFang SC, Noto Sans CJK SC, Microsoft YaHei, sans-serif"}'


def natural_width(svg):
    """Mermaid 默认 width=100% 会把宽图压得很小；改成原始宽度，放不下时横向滚动"""
    m = re.search(r'max-width:\s*([\d.]+)px;?', svg[:600])
    if not m:
        return svg
    svg = svg.replace(m.group(0), "", 1)
    return re.sub(r'width="100%"', f'width="{float(m.group(1)):.0f}"', svg, count=1)


def prerender(sources):
    """用无头浏览器把 Mermaid 源码渲染成 SVG；不可用时返回 None"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page_ = browser.new_page()
            page_.set_content("<!doctype html><html><body></body></html>")
            page_.add_script_tag(path=str(MERMAID_JS))
            result = page_.evaluate(
                """async ([cfg, srcs]) => { mermaid.initialize(JSON.parse(cfg)); const out = [];
                for (let i = 0; i < srcs.length; i++) {
                  try { const r = await mermaid.render('mmd' + i, srcs[i]); out.push({ svg: r.svg }); }
                  catch (e) { out.push({ err: String((e && e.message) || e) }); } }
                return out; }""", [MERMAID_CFG, sources])
            browser.close()
            return result
    except Exception as e:  # 浏览器装不上、启动失败等
        print(f"提示：Playwright 无法启动浏览器（{type(e).__name__}），改为内联渲染库", file=sys.stderr)
        return None


lib = ""
if MERMAIDS:
    if not MERMAID_JS.is_file():
        sys.exit(f"缺少 {MERMAID_JS}；请完整安装本 skill（含 assets/vendor/）")
    rendered = prerender(MERMAIDS) if MODE in ("auto", "static") else None
    if MODE == "static" and rendered is None:
        sys.exit("--mermaid static 需要 Python playwright 和可用的 Chromium；可改用 --mermaid inline")
    bad = 0
    for i, src in enumerate(MERMAIDS):
        r = rendered[i] if rendered else None
        if r and "svg" in r:
            body = f'<div class="mermaid-svg">{natural_width(r["svg"])}</div>'
        else:
            if r:
                bad += 1
                print(f"Mermaid 图 {i + 1} 语法错误，已以源码显示：{r['err'][:200]}\n---\n{src[:300]}", file=sys.stderr)
            body = f'<div class="mermaid">{E(src)}</div>'
        page = page.replace(f"\x00MERMAID{i}\x00", body)
    if rendered is None:  # 内联渲染库，离线打开时在浏览器里渲染
        lib = "<script>" + MERMAID_JS.read_text(encoding="utf-8").replace("</script", "<\\/script") + "</script>\n"
    mode_used = "static" if rendered else "inline"
    print(f"Mermaid 图 {len(MERMAIDS)} 张，方式 {mode_used}" + (f"，其中 {bad} 张语法错误" if bad else ""))
page = page.replace("MERMAID_CFG", MERMAID_CFG).replace("<script type=\"module\">", lib + "<script type=\"module\">", 1)

(OUT / "report.html").write_text(page, encoding="utf-8")
print("report.html", len(page))
