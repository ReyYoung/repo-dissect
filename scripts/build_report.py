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
MERMAID_AT = []  # 每张图所在的章节和小节，用于提示
HINTS = []  # 生成完统一打印的提示（规模超限、首屏写法等）
SKILL_VERSION = ""
try:
    SKILL_VERSION = (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()
except OSError:
    pass
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


# ---- 表格列宽：中文能在任意两个字之间换行，浏览器自动分配列宽时会把中文列压成一两个字宽，
#      所以 3 列以上的表按内容估算每列宽度，用 <colgroup> 定下来（放不下时横向滚动）
_CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef]")
_TOKEN = re.compile(r"[^\s\u2e80-\u9fff\uf900-\ufaff\u3000-\u303f\uff00-\uffef]+")
_LINE_EM = {3: 20, 4: 14, 5: 12}  # 每列一行最多放多少个字宽（列越多越窄）


def _em(s):
    return sum(1.0 if _CJK.match(c) else 0.56 for c in s)


def _plain(cell):
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", cell)
    s = re.sub(r"\[([^\]]+)\]\([^)\s]+\)", r"\1", s)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = s.replace("**", "").replace("`", "")
    for mark in ("✅", "🔍", "❓"):
        s = s.replace(mark, "事实")  # 会变成小标签，宽度约两个字
    return s


def _colgroup(head, rows):
    """返回 (<table ...> 开始标签含 <colgroup>)；少于 3 列返回 None。
    need：每列至少要多宽（px），want：空间宽裕时希望多宽；页面脚本按实际宽度在两者之间分配，没有脚本时按 need 的比例"""
    n = len(head)
    if n < 3:
        return None
    line = _LINE_EM.get(n, 9)
    need, want = [], []
    for j in range(n):
        cells = [_plain(r[j]) for r in rows if j < len(r)]
        longest = max([_em(x) for c in cells for x in c.split("\n")] or [0])
        token = min(14, max([_em(t) for c in cells for t in _TOKEN.findall(c)] or [0]))
        head_em = _em(_plain(head[j]))
        w = max(min(longest, line), token, min(head_em, 8), 2.5)
        need.append(round(w * 13.5 + 30))  # 按 13.5px 字号估（Windows 上表格字号），左右内边距 28px
        want.append(round(max(w, min(longest, line * 2.5), min(head_em, 12)) * 13.5 + 30))
    total = sum(need)
    cols = "".join(f'<col style="width:{w / total * 100:.1f}%">' for w in need)
    return (f'<table class="fixed" style="min-width:{total}px" data-need="{",".join(map(str, need))}" '
            f'data-want="{",".join(map(str, want))}"><colgroup>{cols}</colgroup>')


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
            open_tag = _colgroup(head, rows) or "<table>"
            out.append(f"{open_tag}\n<thead>\n<tr>{th}</tr>\n</thead>\n<tbody>\n{trs}</tbody>\n</table>")
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
    # 文字色都与底色保持 5:1 以上对比，小字号标签也看得清
    "good": ("#E2F3E8", "#1A6B39"), "info": ("#E0F5F9", "#066A7D"), "warn": ("#FCF0DC", "#8A5000"),
    "bad": ("#FBE9E9", "#A82C2C"), "default": ("#ECEEF4", "#59627A"), "brand": (P50, P700),
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
        MERMAID_AT.append(f"{label}「{name}」")
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
    body = re.sub(r"<table\b", '<div class="table-wrap"><table', body).replace("</table>", "</table></div>")
    body = re.sub(r"<blockquote>", '<div class="alert info"><span class="dot">i</span><div>', body)
    body = body.replace("</blockquote>", "</div></div>")
    body = re.sub(r'<a href="(https?://[^"]+)"', r'<a href="\1" target="_blank" rel="noopener"', body)
    # 标题加锚点
    n = [0]

    def hid(m):
        n[0] += 1
        return f'<{m.group(1)} id="{sec_id}-{n[0]}">'
    body = re.sub(r"<(h[234])>", hid, body)
    # "附录：完整功能清单"、"证据明细" 之类的长内容折叠起来（文件里的 ## 或 ### 标题）
    for lv, stop in (("4", "234"), ("3", "23")):
        body = re.sub(rf'<h{lv} id="[^"]+">((?:[\d.、\s]+)?(?:附录|证据明细)[^<]*)</h{lv}>(.*?)(?=<h[{stop}] |$)',
                      lambda m: f'<details class="collapse"><summary>{m.group(1)}</summary>{m.group(2)}</details>',
                      body, flags=re.S)
    return body


# ---- Mermaid 图规模：和 charts-and-report.md 第 2 节的上限一致
_ARROW = re.compile(r"\s*(?:<?[-=.]{2,}[->xo]?>?|<?-\.+->?|&)\s*")
_ID = r"[A-Za-z_一-鿿0-9][\w一-鿿-]*"


def _flow_nodes(body):
    nodes = set()
    stmts = [x.strip() for ln in body for x in re.sub(r'"[^"]*"', '""', ln).split(";") if x.strip()]
    for ln in stmts:
        if re.match(r"(subgraph|end\b|classDef|class\s|style\s|linkStyle|click\s|direction)", ln):
            continue
        t = ln
        t = re.sub(r"\|[^|]*\|", " ", t)                       # -->|标签|
        t = re.sub(r"@\{[^{}]*\}", "", t)                       # A@{ shape: ... }
        t = re.sub(r"\b\w+@(?=[-=.<])", "", t)                  # 边的 id：e1@-->
        for _ in range(3):                                      # 各种形状里的文字
            t = re.sub(r"\[[^\[\]]*\]|\([^()]*\)|\{[^{}]*\}|(?<=[\w一-鿿])>[^\]]*\]", "", t)
        t = re.sub(r"(?:--|==|-\.)(?![->.=])\s*[^-=.>]+?\s*(?=-->|---|==>|===|\.->|\.-)", "", t)  # A -- 文字 --> B
        t = re.sub(r":::[\w-]+", "", t)
        for tok in _ARROW.split(t):
            tok = tok.strip(" ;")
            if re.fullmatch(_ID, tok):
                nodes.add(tok)
    return nodes


def _states(body):
    st = set()
    for ln in body:
        if re.match(r"(classDef|class\s|style\s|note\b|end note|direction\b|--$|\}|\[\*\]\s*$)", ln):
            continue
        m = re.match(r'state\s+(?:"[^"]*"\s+as\s+)?([\w一-鿿]+)', ln)
        if m:
            st.add(m.group(1))
            continue
        ln = re.split(r"\s*:\s*", ln, maxsplit=1)[0]                     # 去掉转移上的说明
        for tok in re.split(r"\s*-->\s*", ln):
            tok = tok.strip()
            if re.fullmatch(r"[\w一-鿿]+", tok):
                st.add(tok)
    return st


def mermaid_size(src):
    """返回 (图型, {指标: (数量, 上限)})；认不出的图返回 (None, {})。只用于提示，数得不准也不影响生成"""
    lines = [ln.strip() for ln in src.splitlines() if ln.strip() and not ln.strip().startswith("%%")]
    if not lines:
        return None, {}
    head = lines[0].split()[0]
    body = lines[1:]
    if head == "sequenceDiagram":
        parts, msgs = set(), 0
        for ln in body:
            m = re.match(r"(?:create\s+)?(?:participant|actor)\s+([^\s@]+)", ln)
            if m:
                parts.add(m.group(1))
                continue
            m = re.match(r"([^\s:+-][^:]*?)\s*(?:<<-{1,2}>>|-{1,2}>>|-{1,2}>|-{1,2}x|-{1,2}\))\s*[+-]?\s*([^:]+?)\s*:", ln)
            if m:
                msgs += 1
                parts.update([m.group(1).strip(), m.group(2).strip()])
        return "时序图", {"参与者": (len(parts), 6), "消息": (msgs, 12)}
    if head in ("flowchart", "graph"):
        kind, lim = ("流程图", 12) if head == "flowchart" else ("依赖图", 15)
        return kind, {"节点": (len(_flow_nodes(body)), lim)}
    if head.startswith("stateDiagram"):
        return "状态图", {"状态": (len(_states(body)), 8)}
    if head == "erDiagram":
        ents = set()
        for ln in body:
            m = (re.match(r'("[^"]+"|[\w-]+)\s+[|}o][|o]?(?:--|\.\.)[|o{]{1,2}\s+("[^"]+"|[\w-]+)', ln)
                 or re.match(r'("[^"]+"|[\w-]+)(?:\[[^\]]*\])?\s*\{', ln))
            if m:
                ents.update(g for g in m.groups() if g)
        return "ER 图", {"实体": (len(ents), 12)}
    return None, {}


secs, nav = [], []
for i, s in enumerate(CFG["sections"]):
    fname, label = s[0], s[1]
    if Path(fname).name.lower() == "index.md":
        print("提示：index.md 是过程记录，不建议放进报告章节；范围和方法写进 report.json 的 about，待确认事项写进 pending")
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

if SKILL_VERSION and CFG.get("about") is not None:
    _ab = []
    for x in CFG["about"]:
        if isinstance(x, (list, tuple)) and x and str(x[0]) == "技能版本":
            continue  # 旧的版本行去掉，统一在最后写当前版本
        _ab.append(x)
    CFG["about"] = _ab + [["技能版本", f"repo-dissect v{SKILL_VERSION}"]]
# 文末固定两块：待确认清单（pending）、报告说明（about：制作统计、方法、证据边界）
END = (("pending", "待确认清单", "还没能用代码或运行坐实、需要人工确认的事项"),
       ("about", "报告说明", "这份报告是怎么做出来的：范围、方法、制作统计和证据边界"))
for key, label, hint in END:
    items = CFG.get(key) or []
    if not items:
        continue
    lis = []
    for it in items:  # 字符串，或 [标题, 说明]
        if isinstance(it, (list, tuple)):
            k, val = (list(it) + [""])[:2]
            lis.append(f"<li><strong>{_inline(str(k))}</strong>：{_inline(str(val))}</li>")
        else:
            lis.append(f"<li>{_inline(str(it))}</li>")
    sid = f"end-{key}"
    n = len(secs) + 1
    secs.append(f'<section class="sec endcard" id="{sid}" data-label="{E(label)}"><h2><span class="secno">{n:02d}</span>{E(label)}</h2>'
                f'<p class="aux">{E(hint)}</p>{_retag("<ul>" + "".join(lis) + "</ul>")}</section>')
    nav.append(f'<a href="#{sid}" data-sec="{sid}"><span class="ico"></span>{E(label)}</a>')

# 首屏写法检查：关键数字别放制作指标；结论里的全称词要有范围
_PROD = re.compile(r"代码引用|引用数|核验|份(分层)?文档|文档数|分析.{0,4}文件|精读|完成.{0,3}层|子代理|L[0-5]\b")
for item in CFG.get("stats", []):
    m = _PROD.search(str(item[1]))  # 只看标签：补充说明里提到"引用"不算
    if m:
        HINTS.append(f"首屏关键数字「{item[1]}」像是报告的制作指标（{m.group(0)}），"
                     "应放进 about（报告说明）；首屏只放项目本身的事实")
_ALL = re.compile(r"全部|所有|唯一|没有|只能|不会|一律|完全|从不|永远|必然|绝对|保证|确保|无回归|只进不出|无测试")
_SCOPE = re.compile(r"在.{0,20}(范围|中|里|内)|范围|检索|扫描|未找到|没找到|本 ?commit|默认|根目录|开源版|社区版|按")
try:
    _INDEX = (OUT / "index.md").read_text(encoding="utf-8")
except OSError:
    _INDEX = ""
_FRONT = [str(CFG["verdict"].get("summary", ""))] + [str(x) for x in CFG["verdict"].get("points", [])]
for item in CFG.get("stats", []):  # 关键数字的标签和补充说明也算首屏结论（如"核心路径无回归保护"）
    vals = list(item)[:3]
    if vals and re.search(r"\d", str(vals[0])):
        vals = vals[1:]  # 数值本身不查；"无""全部"这类文字型数值要查
    _FRONT.append("；".join(str(x) for x in vals if x))
for t in _FRONT:
    m = _ALL.search(t)
    if not m or _SCOPE.search(t):
        continue
    key = re.sub(r"\s", "", t)[:10]
    if key and key in re.sub(r"\s", "", _INDEX):
        continue  # 核对表里已有这条
    short = t if len(t) <= 40 else t[:40] + "…"
    HINTS.append(f"首屏结论或关键数字里有「{m.group(0)}」又没写范围：「{short}」——写清在什么范围、用什么方法得出，"
                 "并在 index.md 的关键结论核对表里加一行；撑不起就改弱")
# 技能版本写进页脚和报告说明，方便事后追溯
if SKILL_VERSION:
    stamp = f"repo-dissect v{SKILL_VERSION}"
    ft = str(CFG.get("footer", ""))
    if re.search(r"repo-dissect v[\d.]+", ft):
        CFG["footer"] = re.sub(r"repo-dissect v[\d.]+", stamp, ft)  # 增量更新时换成当前版本
    elif "由 repo-dissect 生成" in ft:
        CFG["footer"] = ft.replace("由 repo-dissect 生成", f"由 {stamp} 生成")
    else:
        CFG["footer"] = ((ft.rstrip() + " · ") if ft else "") + f"由 {stamp} 生成"

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
--ctl:#8694B6;--weak:#697189;--sub:#59627A;--ink:#181D2B;--ink2:#3C4356;--warn:#A25E00;--navh:0px}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,*::before{transition:none!important;animation:none!important}}
a:focus-visible,.btn:focus-visible,summary:focus-visible{outline:2px solid var(--p600);outline-offset:2px;border-radius:4px}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei UI","Microsoft YaHei","Noto Sans SC","Source Han Sans SC",sans-serif;font-variant-numeric:tabular-nums}
/* Windows：多为普通密度屏幕、雅黑小字号偏细，正文放大一号、文字加深（.win 由页头脚本按系统加上） */
.win body{font-size:15px}.win .sec p,.win .sec li,.win td{color:#2A3040}.win table{font-size:13.5px}.win th{font-size:13px}
.win .tag.sm{font-size:12px}.win code{font-size:13px}.win .stat .sl,.win .stat .sn,.win .crumb,.win figcaption,.win .anchor{font-size:13px}
a{color:var(--p600);text-decoration:none}a:hover{text-decoration:underline}
.layout{display:grid;grid-template-columns:232px minmax(0,1fr) 200px;min-height:100vh}
/* 侧边导航：宽 232 · 白底右描边 · 当前项强调色浅底 */
.side{position:sticky;top:0;height:100vh;overflow:auto;background:#fff;border-right:1px solid var(--card);padding:14px 10px}
.brand{display:flex;gap:10px;align-items:center;padding:6px 10px 16px}
.brand .mk{width:30px;height:30px;border-radius:8px;background:var(--p600);color:#fff;font-weight:700;font-size:13px;display:flex;align-items:center;justify-content:center}
.brand img.logo{width:34px;height:34px;background:none;border-radius:0;object-fit:contain;flex:none}
.brand b{display:block;font-size:13.5px}.brand small{display:block;font-size:11.5px;color:var(--weak);font-weight:600;letter-spacing:.04em}
.side nav{display:flex;flex-direction:column;gap:2px}
.side nav a{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:7px;color:var(--sub);font-size:13.5px;text-decoration:none}
.side nav a:hover{background:var(--bg)}
.side nav a .ico{width:8px;height:8px;border-radius:2.5px;background:var(--weak);flex:none}
.side nav a.on{background:var(--p50);color:var(--p700);font-weight:600}.side nav a.on .ico{background:var(--p600)}
.side .grp{font-size:12px;color:var(--weak);font-weight:600;padding:14px 12px 6px}
.main{padding:24px 32px 80px;min-width:0}
.crumb{font-size:12.5px;color:var(--weak);margin-bottom:10px}.crumb .sep{margin:0 6px;color:var(--ctl)}
.head{display:flex;align-items:flex-start;gap:16px;margin-bottom:18px}
h1{font-size:26px;font-weight:700;line-height:1.35;margin:0}
.aux{font-size:13px;color:var(--weak);margin-top:4px}
.btn{font:500 12.5px inherit;font-family:inherit;height:30px;padding:0 12px;border-radius:6px;border:1px solid var(--ctl);background:#fff;color:var(--ink2);cursor:pointer;white-space:nowrap}
.btn:hover{border-color:var(--p600);color:var(--p600)}
.head .btn{margin-left:auto}
.card{background:#fff;border:1px solid var(--card);border-radius:12px;padding:24px 28px;margin-bottom:16px}
.verdict{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:28px}
.verdict h2{font-size:20px;line-height:1.4;margin:10px 0 8px}
.verdict ol{margin:6px 0 0;padding-left:20px;color:var(--ink2)}.verdict li{margin:4px 0}
.desc{display:grid;grid-template-columns:auto 1fr;border:1px solid var(--card);border-radius:8px;overflow:hidden;font-size:13px;align-self:start}
.desc .dk{padding:8px 12px;background:var(--bg);color:var(--sub);border-bottom:1px solid var(--line);white-space:nowrap}
.desc .dv{padding:8px 12px;border-bottom:1px solid var(--line);word-break:break-all}
.desc .dk:nth-last-child(2),.desc .dv:last-child{border-bottom:none}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:16px}
.stat{background:#fff;border:1px solid var(--card);border-radius:12px;padding:14px 18px}
.stat .sl{font-size:12.5px;color:var(--weak)}.stat .sv{font-size:24px;font-weight:700;line-height:1.35;margin-top:2px}
.stat .sn{font-size:12.5px;color:var(--sub);margin-top:2px}
.tag{display:inline-block;font-size:12px;font-weight:600;padding:2px 9px;border-radius:4px;white-space:nowrap;line-height:1.6;vertical-align:1px}
.tag.sm{font-size:11.5px;padding:0 6px;margin:0 2px}
.alert{display:flex;gap:10px;align-items:flex-start;border-radius:8px;padding:10px 14px;font-size:13px;margin:12px 0}
.alert .dot{width:16px;height:16px;border-radius:99px;color:#fff;font-size:11px;font-weight:700;display:inline-flex;align-items:center;justify-content:center;flex:none;margin-top:3px}
.alert.warn{background:#FCF0DC;border:1px solid #F4D9AE;color:#8A5200}.alert.warn .dot{background:#D17A00}
.alert.info{background:#F2FAFC;border:1px solid #C5E8EF;color:#3C4356}.alert.info .dot{background:#066A7D}
.alert p{margin:2px 0}
.sec{background:#fff;border:1px solid var(--card);border-radius:12px;padding:8px 28px 26px;margin-bottom:16px;scroll-margin-top:calc(var(--navh) + 16px)}
.sec h2{font-size:20px;font-weight:700;line-height:1.4;margin:22px 0 12px;display:flex;align-items:baseline;gap:10px}
.secno{font:700 12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--weak)}
.sec h3{font-size:16px;font-weight:600;line-height:1.5;margin:26px 0 8px;scroll-margin-top:calc(var(--navh) + 16px)}
.sec h4{font-size:14px;font-weight:600;margin:18px 0 6px;scroll-margin-top:calc(var(--navh) + 16px)}
#top{scroll-margin-top:calc(var(--navh) + 16px)}
.sec p,.sec li{color:var(--ink2);overflow-wrap:anywhere}
.sec strong{color:var(--ink)}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Cascadia Mono","Liberation Mono",monospace;font-size:12.5px;background:var(--line);color:var(--ink2);padding:1px 5px;border-radius:4px;overflow-wrap:anywhere}
pre{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Cascadia Mono","Liberation Mono",monospace;background:var(--bg);border:1px solid var(--card);border-radius:8px;padding:12px 14px;overflow-x:auto}pre code{background:none;padding:0}
.table-wrap{border:1px solid var(--card);border-radius:10px;overflow-x:auto;margin:12px 0 18px;position:relative}
.scroll-hint{display:none;font-size:12px;color:var(--weak);margin:12px 0 -6px}.scroll-hint.show{display:block}
.table-wrap.scrollable th:first-child,.table-wrap.scrollable td:first-child{position:sticky;left:0;z-index:1;box-shadow:1px 0 0 var(--card)}
.table-wrap.scrollable th:first-child{background:var(--bg)}.table-wrap.scrollable td:first-child{background:#fff}
.table-wrap.scrollable tr:hover td:first-child{background:var(--bg)}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:640px}
th{background:var(--bg);font-size:12.5px;font-weight:600;color:var(--sub);text-align:left;padding:10px 14px;white-space:nowrap}
td{padding:10px 14px;border-top:1px solid var(--line);vertical-align:top;color:var(--ink2);overflow-wrap:anywhere}
table.fixed{table-layout:fixed}table.fixed th{white-space:normal}
tr:hover td{background:var(--bg)}
figure.diagram{margin:14px 0 20px;border:1px solid var(--card);border-radius:10px;padding:16px;background:#fff}
.fig-scroll{overflow-x:auto}.fig-scroll svg{min-width:760px;display:block}
figure.fit .fig-scroll svg{min-width:0;width:100%;height:auto}
figure.fit .mermaid-svg svg,figure.fit .mermaid svg{max-width:100%!important;width:100%!important;height:auto}
.mermaid{overflow-x:auto;text-align:center}.mermaid:not([data-processed]){white-space:pre;font:12px ui-monospace,monospace;color:var(--weak)}
.mermaid svg{max-width:100%;height:auto}
.mermaid-svg{overflow-x:auto;text-align:center}.mermaid-svg svg{max-width:none;height:auto}
.mermaid[data-processed] svg{max-width:none!important;height:auto}
figcaption{font-size:13px;color:var(--weak);margin-top:10px}
.figbar{display:flex;gap:8px;margin-top:10px}.figbar .btn{height:26px;padding:0 10px}
details.collapse{border:1px solid var(--card);border-radius:8px;margin:14px 0;padding:0 16px}
details.collapse>summary{cursor:pointer;padding:10px 0;font-weight:600;font-size:13.5px;color:var(--ink);list-style:none}
details.collapse>summary::before{content:"▸";display:inline-block;width:16px;color:var(--weak);transition:transform .15s}
details.collapse[open]>summary::before{transform:rotate(90deg)}
details.collapse.big{border:none;margin:0;padding:0}details.collapse.big>summary{font-size:20px;padding:22px 0 12px;display:flex;gap:10px;align-items:baseline}
/* 锚点目录（长文档页） */
.anchor{position:sticky;top:0;height:100vh;overflow:auto;padding:28px 16px 28px 0;font-size:13px}
.anchor .chap{display:none}
.toc-btn{display:none;position:fixed;right:16px;bottom:16px;z-index:7;height:38px;padding:0 16px;border-radius:99px;box-shadow:0 4px 14px rgba(24,29,43,.16)}
.endcard h2{font-size:18px;margin:4px 0 10px}.endcard ul{margin:0;padding-left:20px;color:var(--ink2)}.endcard li{margin:4px 0}
.anchor .t{font-size:12.5px;font-weight:600;color:var(--sub);margin-bottom:10px}
.anchor a{display:block;padding:5px 0 5px 14px;border-left:2px solid var(--line);color:var(--sub);text-decoration:none;line-height:1.5}
.anchor a.l4{padding-left:26px}.anchor a.on{border-left-color:var(--p600);color:var(--p600);font-weight:600}
footer{font-size:12.5px;color:var(--weak);margin-top:24px}
@media (max-width:1499px){.layout{grid-template-columns:232px minmax(0,1fr)}
.anchor{display:none;position:fixed;top:auto;right:16px;bottom:64px;z-index:8;height:auto;max-height:65vh;width:min(320px,calc(100vw - 32px));background:#fff;border:1px solid var(--card);border-radius:12px;padding:14px 16px;box-shadow:0 8px 28px rgba(24,29,43,.18)}
.anchor.open{display:block}.toc-btn{display:inline-flex;align-items:center}}
@media (max-width:860px){.layout{display:block}.side{position:sticky;top:0;z-index:5;height:auto;padding:8px 12px;border-right:none;border-bottom:1px solid var(--card)}
.brand{display:none}.side .grp{display:none}.side nav{flex-direction:row;overflow-x:auto;gap:4px}.side nav a{white-space:nowrap;padding:6px 10px}
.main{padding:16px 16px 60px}.verdict{grid-template-columns:1fr}.sec{padding:4px 16px 18px}.card{padding:18px}
:root{--navh:56px}.head{flex-wrap:wrap}.head .btn{margin-left:0}.anchor .chap{display:block;margin-bottom:12px}
.anchor .chap a{border-left:none;padding-left:0}h1{font-size:22px}}
@media print{.side,.anchor,.btn,.figbar,.toc-btn,.scroll-hint{display:none!important}figure.diagram svg{min-width:0!important;max-width:100%!important;width:100%!important;height:auto}table{min-width:0!important}.table-wrap{overflow:visible}.layout{display:block}.main{padding:0}.sec,.card,.stat{break-inside:auto;border-color:#ddd}body{background:#fff}details.collapse{display:block}}
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
  const mk = (t, fn) => { const b = document.createElement('button'); b.className = 'btn'; b.type = 'button'; b.textContent = t; b.onclick = fn; bar.append(b); return b; };
  // 宽图：适配宽度 / 原尺寸（窄屏默认适配宽度，看细节时切回原尺寸横向滚动）
  const fitBtn = mk('', () => { fig.classList.toggle('fit'); updFit(); });
  const updFit = () => { const wide = size().w > fig.clientWidth - 34; fitBtn.hidden = !wide && !fig.classList.contains('fit'); fitBtn.textContent = fig.classList.contains('fit') ? '原尺寸' : '适配宽度'; };
  if (size().w > fig.clientWidth - 34 && window.innerWidth <= 860) fig.classList.add('fit');
  updFit(); window.addEventListener('resize', updFit);
  mk('下载 SVG', () => save(URL.createObjectURL(new Blob([svgText()], { type: 'image/svg+xml' })), 'svg'));
  mk('下载 PNG', () => { const { w, h } = size(); const img = new Image(); img.onload = () => { const c = document.createElement('canvas'); c.width = w * 2; c.height = h * 2; const x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, c.width, c.height); x.drawImage(img, 0, 0, c.width, c.height); save(c.toDataURL('image/png'), 'png'); }; img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svgText()); });
  fig.append(bar);
});
// 3) 侧边导航高亮 + 锚点目录随当前章节切换
const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const secs = [...document.querySelectorAll('section.sec')];
const navEl = document.querySelector('.side nav');
const navs = Object.fromEntries([...navEl.querySelectorAll('a')].map(a => [a.dataset.sec, a]));
const anchor = document.querySelector('.anchor .list');
const toc = document.getElementById('toc'), tocBtn = document.querySelector('.toc-btn');
document.querySelector('.anchor .chaplist').append(...[...navEl.querySelectorAll('a')].map(a => { const c = a.cloneNode(true); c.querySelector('.ico')?.remove(); return c; }));
const setNavh = () => { const side = document.querySelector('.side'); document.documentElement.style.setProperty('--navh', window.innerWidth <= 860 ? side.offsetHeight + 'px' : '0px'); };
setNavh(); window.addEventListener('resize', setNavh);
const mark = (id) => {
  Object.values(navs).forEach(a => { const on = a.dataset.sec === id; a.classList.toggle('on', on); on ? a.setAttribute('aria-current', 'location') : a.removeAttribute('aria-current'); });
  toc.querySelectorAll('.chaplist a').forEach(a => a.classList.toggle('on', a.dataset.sec === id));
  const a = navs[id];  // 手机端横向标签：让当前章节保持在可见范围内
  if (a && navEl.scrollWidth > navEl.clientWidth) navEl.scrollTo({ left: a.offsetLeft - navEl.offsetLeft - (navEl.clientWidth - a.offsetWidth) / 2, behavior: reduce ? 'auto' : 'smooth' });
};
let cur = null;
const setSec = (sec) => {
  if (!sec || sec === cur) return; cur = sec;
  mark(sec.id);
  if (!anchor) return;
  anchor.innerHTML = '';
  sec.querySelectorAll('h3[id], h4[id]').forEach(h => { if (h.closest('details:not([open])')) return; const a = document.createElement('a'); a.href = '#' + h.id; a.textContent = h.textContent; if (h.tagName === 'H4') a.className = 'l4'; anchor.append(a); });
  if (!anchor.children.length) anchor.innerHTML = '<div class="aux">本章没有小节</div>';
};
const onScroll = () => {
  const y = window.scrollY + 120 + parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--navh') || 0);
  if (y < secs[0].offsetTop) { cur = null; mark('top'); if (anchor) anchor.innerHTML = getComputedStyle(tocBtn).display === 'none' ? '' : '<div class="aux">滚动到某一章后，这里显示该章小节</div>'; return; }
  let s = secs[0]; for (const x of secs) if (x.offsetTop <= y) s = x;
  if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4)  // 滚到底：最后几章可能顶不到上方
    for (const x of secs) if (x.getBoundingClientRect().top < window.innerHeight * 0.5) s = x;
  setSec(s);
  if (!anchor) return;
  let on = null; anchor.querySelectorAll('a').forEach(a => { const h = document.getElementById(a.getAttribute('href').slice(1)); if (h && h.getBoundingClientRect().top < 140) on = a; });
  anchor.querySelectorAll('a').forEach(a => a.classList.toggle('on', a === on));
};
window.addEventListener('scroll', onScroll, { passive: true }); onScroll();
// 4) 中等屏幕和手机：右下角"目录"按钮展开章节和本章小节
const openToc = (o) => { toc.classList.toggle('open', o); tocBtn.setAttribute('aria-expanded', o); };
tocBtn.addEventListener('click', (e) => { e.stopPropagation(); openToc(!toc.classList.contains('open')); });
toc.addEventListener('click', (e) => { if (e.target.closest('a')) openToc(false); });
document.addEventListener('click', (e) => { if (toc.classList.contains('open') && !toc.contains(e.target)) openToc(false); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') openToc(false); });
// 5) 宽表格：放不下时提示可横向滑动，并固定第一列
const wraps = [...document.querySelectorAll('.table-wrap')];
wraps.forEach(w => { const h = document.createElement('div'); h.className = 'scroll-hint'; h.textContent = '表格较宽，可左右滑动查看 →'; w.before(h); });
// 3 列以上的表：先保证每列最小宽度（need），多出的空间按内容多少分给需要的列（want）
const fitCols = () => document.querySelectorAll('table.fixed[data-need]').forEach(t => {
  const need = t.dataset.need.split(',').map(Number), want = t.dataset.want.split(',').map(Number);
  const W = t.parentElement.clientWidth - 2, sn = need.reduce((a, b) => a + b, 0), sw = want.reduce((a, b) => a + b, 0);
  let ws = need;
  if (W > sn) ws = W >= sw ? want.map(x => x * W / sw) : need.map((x, i) => x + (W - sn) * (want[i] - x) / (sw - sn || 1));
  t.querySelectorAll('col').forEach((c, i) => { c.style.width = ws[i].toFixed(0) + 'px'; });
  t.style.width = ws.reduce((a, b) => a + b, 0).toFixed(0) + 'px';
});
let printing = false;  // 打印时用按比例的列宽，不按屏幕宽度重排
const pctCols = () => document.querySelectorAll('table.fixed[data-need]').forEach(t => {
  const need = t.dataset.need.split(',').map(Number), sn = need.reduce((a, b) => a + b, 0);
  t.style.width = ''; t.querySelectorAll('col').forEach((c, i) => { c.style.width = (need[i] / sn * 100).toFixed(1) + '%'; });
});
const fitTables = () => { if (printing) return; fitCols(); wraps.forEach(w => { const sc = w.scrollWidth > w.clientWidth + 2; w.classList.toggle('scrollable', sc); w.previousElementSibling.classList.toggle('show', sc); }); };
fitTables(); window.addEventListener('resize', fitTables);
window.addEventListener('beforeprint', () => { printing = true; pctCols(); });
window.addEventListener('afterprint', () => { printing = false; setTimeout(fitTables, 0); });
document.addEventListener('toggle', fitTables, true);
// 6) 打印：无论点按钮还是直接用浏览器打印，都先展开折叠内容，打印完恢复
let closed = [];
window.addEventListener('beforeprint', () => { closed = [...document.querySelectorAll('details:not([open])')]; closed.forEach(d => d.open = true); });
window.addEventListener('afterprint', () => { closed.forEach(d => d.open = false); closed = []; });
document.querySelector('[data-print]')?.addEventListener('click', () => window.print());
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
<meta name="viewport" content="width=device-width,initial-scale=1">
<script>if(/Windows/i.test(navigator.userAgent))document.documentElement.classList.add('win')</script><title>{E(CFG['title'])}</title>
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
<aside class="anchor" id="toc" aria-label="目录"><div class="chap"><div class="t">章节</div><div class="chaplist"></div></div>
<div class="t">本章目录</div><div class="list"></div></aside>
<button class="btn toc-btn" type="button" aria-expanded="false" aria-controls="toc">目录</button>
</div>{JS}</body></html>"""

# ---- Mermaid：预渲染成静态 SVG，或内联渲染库 ----
# 关闭 HTML 标签，否则导出 PNG 时画布会被浏览器判定为"被污染"而失败；
# 字体在这里统一设置（Mermaid 不认 themeVariables 里的 fontFamily）
MERMAID_CFG = '{"startOnLoad": false, "securityLevel": "strict", "htmlLabels": false, "flowchart": {"htmlLabels": false}, "fontFamily": "-apple-system, Segoe UI, PingFang SC, Microsoft YaHei UI, Microsoft YaHei, Noto Sans CJK SC, sans-serif"}'


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

for i, src in enumerate(MERMAIDS):
    kind, sizes = mermaid_size(src)
    over = [f"{k} {n} 个（上限 {lim}）" for k, (n, lim) in sizes.items() if n > lim]
    if over:
        how = "按阶段拆成几张，只负责转交的中间层写进图注" if kind == "时序图" else "拆图或先把同类步骤聚合"
        HINTS.append(f"第 {i + 1} 张 Mermaid 图（{MERMAID_AT[i]}，{kind}）超过规模上限：{'、'.join(over)}；{how}")

(OUT / "report.html").write_text(page, encoding="utf-8")
print("report.html", len(page))
if HINTS:
    print(f"\n交付前请处理以下 {len(HINTS)} 条提示（不影响生成，规则见 references/charts-and-report.md）：")
    for h in HINTS:
        print("  -", h)
