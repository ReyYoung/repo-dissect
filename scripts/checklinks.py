"""核验文档里的代码引用（只用标准库，Python 3.8+）。

用法:
  python3 checklinks.py <src目录> <owner/repo> <sha> 文件1.md [文件2.md ...]        # GitHub 项目
  python3 checklinks.py <src目录> local <sha> 文件1.md ...                          # 本地仓库
  加 --fix：把 GitHub 项目里写成本地路径的引用（如 `api/app.py:12-30`、续行 `:45`）改写成固定 commit 的永久链接
  加 --show：逐条打印每个引用指向的那一行代码，便于抽查"行号在范围内但指错了行"（脚本无法自动判断这类错误）

代码来源:
  <src目录> 是 git 仓库时用 git 读取 <sha> 下的文件；
  不是 git 仓库时（例如用 fetch_repo.py 下载的源码包）读 <src目录>/.rd-manifest.json 的文件清单，直接读磁盘文件，
  并核对清单里的 commit 与 <sha> 一致；没有清单时按磁盘文件核验，并提示"未核对版本"。

核验内容:
  1. 永久链接 https://github.com/<owner/repo>/blob/<sha>/<path>#L10-L20：commit 必须是本次固定的 sha，
     文件存在，行号不越界；路径支持 ( ) [ ] 等字符（如 Next.js 的 app/(main)/[id]/page.tsx）
  2. 本地路径写法 `path:10`、`path:10-20`、`path:L10-L20`：同样核验文件和行号；
     路径不完整（如只写文件名）时，若在仓库里唯一匹配就按完整路径核验并提示补全
  3. 续行写法 `:45`、`:45-60`：沿用同一小节里最近一次出现的完整路径；小节里没有完整路径时报错
  4. GitHub 项目里出现本地路径或续行写法 → 报"未写成永久链接"（可用 --fix 自动改写）
  5. 编号开头的分层文档（00-、01-……）一条代码引用都没有 → 报错，不能算核验通过
  6. 占位引用 → 报错：单行引用指向空行、只有括号的行，或文件第 1 行的 import / package / {
     这类文件开头内容——它们只能说明"文件在这"，证明不了结论；请改指到真正证明结论的行
  7. 核心模块精读（04- 开头的文档）缺少规定的六块内容 → 报错（见 references/layers.md L4）
  8. 有 04- 文档时，同目录的 index.md 要写"选题依据"（用户选择的原话、明确委托的原话，或"小仓库，按候选表自选"）→ 没写报错；
     index.md 还没写时只提示（见 SKILL.md 第 0 节"需要用户拿主意的地方"）
  9. 同目录有 index.md 但没有「关键结论核对表」时提示（不影响退出码）
  提示（不影响退出码）:
  - 标了 ✅ 的行里没有行号级代码引用（标题行、表头、同一行写了检索或 git 命令作证据的除外）
  - 绝对化用语（必然、绝对、确保、100% 等），提醒复核证据是否撑得起这么强的说法
  - 全称句（一律、唯一、只能、从不、无回归等；主流程、精读和 compare.md 里还包括"所有、全部"）写进各文档所在目录的
    _全称句清单.txt（每份文档最多 12 句、每个目录最多 60 句；已写明范围、带 ❓ 或"是否"的句子不列；
    没有全称句时删掉旧清单），交付前逐条对照同章正文、表格和待确认清单
对比模式下对每个仓库各运行一次（compare.md 每次都带上）。发现问题时退出码为 1。
"""
import json
from collections import Counter
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

for _s in (sys.stdout, sys.stderr):  # Windows 中文控制台（GBK）打印 ✅ 会崩
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

args = sys.argv[1:]
FIX = "--fix" in args
SHOW = "--show" in args
args = [a for a in args if a not in ("--fix", "--show")]
if len(args) < 4:
    sys.exit(__doc__)
src, repo, sha, files = args[0], args[1], args[2], args[3:]
LOCAL = repo == "local"
if not re.fullmatch(r"[0-9a-f]{40}", sha):
    sys.exit(f"<sha> 需要 40 位完整 commit 号，现在是 {sha!r}；git 仓库用 git -C <src> rev-parse HEAD，"
             "源码包看 <src>/.rd-manifest.json 的 sha")
if FIX and LOCAL:
    sys.exit("--fix 只用于 GitHub 项目（本地仓库本来就用 path:行号 写法）")

# ---------------------------------------------------------------- 代码来源：git 或磁盘
SRC = Path(src)
GIT = (SRC / ".git").exists() and subprocess.run(["git", "-C", src, "cat-file", "-e", sha + "^{commit}"],
                                                capture_output=True).returncode == 0
NOTE = ""
if GIT:
    r = subprocess.run(["git", "-C", src, "ls-tree", "-r", "--name-only", "-z", sha], capture_output=True)
    if r.returncode:
        sys.exit(f"读取 {src} 在 {sha[:12]} 的文件列表失败：{r.stderr.decode('utf-8', 'replace').strip()[:200]}")
    TREE = set(x for x in r.stdout.decode("utf-8", "replace").split("\0") if x)
else:
    if (SRC / ".git").exists():
        sys.exit(f"{src} 是 git 仓库，但里面没有 commit {sha[:12]}：先 git -C {src} fetch 或检查 sha")
    man = SRC / ".rd-manifest.json"
    if man.is_file():
        m = json.loads(man.read_text(encoding="utf-8"))
        if m.get("sha") not in (sha, "unknown"):
            sys.exit(f"源码包的 commit 是 {str(m.get('sha'))[:12]}，与要核验的 {sha[:12]} 不一致")
        TREE = set(m.get("files") or {})
        NOTE = f"（源码包，来源 {m.get('source', '未知')}，按清单核验" + \
            ("；源码包没有记录 commit，版本未核对）" if m.get("sha") == "unknown" else "）")
    elif SRC.is_dir():
        TREE = {p.relative_to(SRC).as_posix() for p in SRC.rglob("*") if p.is_file() and ".git" not in p.parts}
        NOTE = "（注意：不是 git 仓库也没有 .rd-manifest.json，按磁盘文件核验，未核对版本）"
    else:
        sys.exit(f"找不到代码目录 {src}")
BY_NAME = {}
for p in TREE:
    BY_NAME.setdefault(p.rsplit("/", 1)[-1], []).append(p)

cache = {}


def file_lines(path):
    if path not in cache:
        data = None
        if GIT:
            rr = subprocess.run(["git", "-C", src, "show", f"{sha}:{path}"], capture_output=True)
            data = None if rr.returncode else rr.stdout
        else:
            try:
                data = (SRC / path).read_bytes()
            except OSError:
                data = None
        lines = None if data is None else data.decode("utf-8", "replace").split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        cache[path] = lines
    return cache[path]


def nlines(path):
    ls = file_lines(path)
    return None if ls is None else len(ls)


# ---------------------------------------------------------------- 正则
# 永久链接：路径先贪心取到 # 或空白为止，再在 resolve_perma 里去掉 Markdown 链接收尾的 )
PERMA = re.compile(r"https://github\.com/" + (re.escape(repo) if not LOCAL else r"[^/\s]+/[^/\s]+")
                   + r"/blob/([^/\s)]+)/([^#\s`<>\"']+)(?:#L(\d+)(?:-L(\d+))?)?")
# `path:10` / `path:10-20` / `path:L10-L20`；路径可含 ( ) [ ] @ 等字符，要有字母开头的扩展名
LOCALREF = re.compile(r"(?<!\[)`([^\s`:]+\.[A-Za-z][A-Za-z0-9]*):L?(\d+)(?:\s*[-–]\s*L?(\d+))?`")
# 续行 `:45` / `:45-60` / `:L45-L60`
CONT = re.compile(r"(?<!\[)`:L?(\d+)(?:\s*[-–]\s*L?(\d+))?`")
# 续行写法前面紧挨着这些词时是端口号，不是行号（端口建议写成 `8080` 或 `localhost:8080`）
PORT_CTX = re.compile(r"(端口|监听|映射|暴露|地址|port|listen|expose|host)[^`\n]{0,6}$", re.I)
# `github.com:443` 这类主机名加端口，不是文件引用
HOSTLIKE = re.compile(r"^[^/]+\.(com|org|net|io|cn|dev|ai|co|cc|me|app|cloud|local|internal|svc|xyz|tech)$", re.I)
HEADING = re.compile(r"(?m)^#{1,6}\s")
# 指向目录的永久链接（.../tree/<sha>/dir），算作有出处
TREELINK = re.compile(r"https://github\.com/[^/\s]+/[^/\s]+/tree/[0-9a-f]{7,40}/")
FENCE = re.compile(r"^```.*?^```", re.S | re.M)
CMD_EVIDENCE = re.compile(r"`(?:git|gh|rg|grep|find|ls|wc|tokei|cloc|curl|docker)\s[^`]+`|`[^`]*repo_stats\.py[^`]*`|_stats\.json")
UNIVERSAL = re.compile(r"一律|唯一|只能|只有|从不|永远|始终|总是|绝不|没有任何|无任何|全都|均会|只进不出|无回归|没有测试|无测试|不存在|完全")
UNIVERSAL_DEEP = re.compile(r"所有|全部")  # 只在 03-、04- 文档里算：这两个词在描述性章节里太常见
SCOPED = re.compile(r"在.{0,20}(范围|中|里|内)|范围内|检索|扫描|未找到|没找到|本 ?commit|默认|按.{0,10}(统计|口径)|口径")
universal = []  # (文件, 行号, 句子, 排序键)
univ_dirs = set()  # 扫描过全称句的目录：没有全称句时也要清掉旧清单
ABSOLUTE = re.compile(r"必然|绝对|确保|保证|(?:100\s*%|百分之百)\s*(?:的)?\s*(?:可靠|准确|正确|安全|可信|成功|兼容|命中|保证)|零风险|毫无风险|万无一失|彻底解决|完全不会|一定会")
# 不能当证据的行：空行、只有括号/标点；以及文件第 1 行的 import、package、shebang 等文件开头内容
TRIVIAL = re.compile(r"^\s*[{}\[\]();,]*\s*$")
HEADER = re.compile(r"^\s*(import\s|from\s+\S+\s+import\s|package\s|use\s|require\(|#include|#!|<\?xml|['\"]use strict['\"])")
# 核心模块精读必须有的六块（标题或加粗小标题里出现任一关键词即可）
L4_BLOCKS = [("解决的问题与输入输出", r"输入|输出|解决的问题"), ("核心机制（算法或不变量）", r"机制|算法|不变量"),
             ("失败边界（出错、降级、限制）", r"失败|边界|降级|异常|限制"), ("设计取舍（替代方案与证据）", r"取舍|替代"),
             ("适用条件与可借鉴之处", r"适用|借鉴"), ("技术债", r"技术债")]


def placeholder(full, a, b):
    """单行引用指向不能当证据的行时，返回说明"""
    if b and int(b) != int(a):
        return ""
    a = int(a)
    line = file_lines(full)[a - 1]
    if TRIVIAL.match(line) or (a == 1 and HEADER.match(line)):
        return f"占位引用（只指向「{line.strip()[:40] or '空行'}」，证明不了结论，请改指到真正的证据行）"
    return ""


def resolve(path):
    """返回 (完整路径, 提示)；找不到返回 (None, 原因)"""
    path = path[2:] if path.startswith("./") else path
    if path in TREE:
        return path, ""
    hits = sorted(p for p in TREE if p.endswith("/" + path)) if "/" in path else sorted(BY_NAME.get(path, []))
    if len(hits) == 1:
        return hits[0], f"路径不完整，应为 {hits[0]}"
    if len(hits) > 1:
        return None, f"路径不完整且有 {len(hits)} 个同名文件（如 {hits[0]}），请写完整路径"
    return None, "文件不存在"


def resolve_perma(path):
    """永久链接里的路径：去掉 Markdown 链接末尾多吃进来的 )，直到能对上仓库里的文件"""
    p = unquote(path)
    if p in TREE:
        return p
    # 依次尝试在每个 ) 处截断（从右往左），能对上仓库文件就用它
    for i in range(len(p) - 1, 0, -1):
        if p[i] == ")" and p[:i] in TREE:
            return p[:i]
    # 都对不上：在第一个不配对的 ) 处截断，报错时显示更干净的路径
    depth = 0
    for i, ch in enumerate(p):
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                return p[:i]
            depth -= 1
    return p


def check_lines(full, a, b):
    total = nlines(full)
    if total is None:
        return "文件读取失败"
    a, b = int(a), int(b or a)
    if b < a:
        return f"行号范围颠倒 L{a}-L{b}"
    if b > total:
        return f"行号越界 L{a}{'-L' + str(b) if b != a else ''}（文件共 {total} 行）"
    return ""


def show_line(full, a, b):
    return f"{full}:{a}" + (f"-{b}" if b and b != a else "") + "  │ " + file_lines(full)[int(a) - 1].strip()[:90]


def perma(full, a, b):
    rng = f"L{a}" + (f"-L{b}" if b and b != a else "")
    return f"[{full}:{rng}](https://github.com/{repo}/blob/{sha}/{full}#{rng})"


bad_total = refs_total = fixed_total = 0
for f in files:
    try:
        text = open(f, encoding="utf-8").read()
    except FileNotFoundError:
        print(f"{f}: 文件不存在，跳过")
        continue
    body = FENCE.sub(lambda m: " " * len(m.group(0)), text)  # 代码块里的不算引用
    heads = [m.start() for m in HEADING.finditer(body)]
    bad, shown, edits, n = [], [], [], 0
    # 永久链接、本地路径、续行写法按出现顺序一起处理，续行沿用同一小节里最近的完整路径
    events = [("P", m) for m in PERMA.finditer(body)] + [("L", m) for m in LOCALREF.finditer(body)] + \
             [("C", m) for m in CONT.finditer(body)]
    events.sort(key=lambda e: e[1].start())
    last_path, last_sec = None, -1
    for kind, m in events:
        if kind == "L" and HOSTLIKE.match(m.group(1)):
            continue
        if kind == "C" and PORT_CTX.search(body[max(0, m.start() - 20):m.start()]):
            continue
        sec = sum(1 for h in heads if h <= m.start())
        if sec != last_sec:
            last_path, last_sec = None, sec
        n += 1
        if kind == "P":
            s, path, a, b = m.groups()
            full = resolve_perma(path)
            if s != sha:
                bad.append(f"commit 不是本次固定的 {sha[:12]}（写成了 {s[:12]}）: {full}")
            elif full not in TREE:
                trunc = not re.search(r"\.[A-Za-z][A-Za-z0-9]*$|(^|/)(Dockerfile|Makefile|LICENSE|README)[^/]*$", full)
                bad.append(("疑似路径被截断或文件不存在" if trunc else "文件不存在") + f": {full}")
            else:
                last_path = full
                if a:
                    msg = check_lines(full, a, b) or placeholder(full, a, b)
                    if msg:
                        bad.append(f"{msg}: {full}#L{a}")
                    elif SHOW:
                        shown.append(show_line(full, a, b))
            continue
        if kind == "L":
            path, a, b = m.groups()
            full, hint = resolve(path)
            where = f"`{path}:{a}{'-' + b if b else ''}`"
            if not full:
                bad.append(f"{hint}: {where}")
                continue
            last_path = full
        else:  # 续行
            a, b = m.groups()
            where = f"`:{a}{'-' + b if b else ''}`"
            if not last_path:
                bad.append(f"续行引用找不到所属文件（同一小节里前面没有完整路径的引用）: {where}")
                continue
            full, hint = last_path, ""
        msg = check_lines(full, a, b) or placeholder(full, a, b)
        if msg:
            bad.append(f"{msg}: {where}" + (f"（续行，文件 {full}）" if kind == "C" else ""))
            continue
        if SHOW:
            shown.append(show_line(full, a, b))
        if not LOCAL:
            if FIX:
                edits.append((m.start(), m.end(), perma(full, a, b)))
            else:
                bad.append(f"未写成永久链接（可加 --fix 自动改写）: {where}" + (f"；{hint}" if hint else "")
                           + (f"（续行，文件 {full}）" if kind == "C" else ""))
        elif hint:
            bad.append(f"{hint}: {where}")
    if edits:
        for s0, e0, new in sorted(edits, reverse=True):
            text = text[:s0] + new + text[e0:]
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(text)
        fixed_total += len(edits)
    name = f.replace("\\", "/").rsplit("/", 1)[-1]
    if n == 0 and re.match(r"\d", name):
        bad.append("没有任何代码引用：分层文档的结论必须对到代码位置（固定 commit 的永久链接或 path:行号）")
    if name.startswith("04-"):
        titles = "\n".join(ln for ln in body.split("\n") if re.match(r"\s*(#{2,6}\s|\*\*|\d+[.、]\s*\*\*)", ln))
        miss = [label for label, pat in L4_BLOCKS if not re.search(pat, titles)]
        if miss:
            bad.append("核心模块精读缺少规定内容（标题里要出现对应关键词）：" + "、".join(miss))
    # 提示：✅ 无引用；绝对化用语
    weak, strong = [], []
    for ln in body.split("\n"):
        s_ = ln.strip()
        if not s_ or s_.startswith("#") or re.fullmatch(r"\|[\s:|-]+\|?", s_):
            continue
        has_ref = PERMA.search(ln) or LOCALREF.search(ln) or CONT.search(ln) or CMD_EVIDENCE.search(ln) or TREELINK.search(ln)
        if "✅" in ln and "🔍" not in ln and "❓" not in ln and not has_ref and not s_.startswith("| ✅"):
            weak.append(s_)
        if ABSOLUTE.search(re.sub(r"`[^`]*`", "", ln)):
            strong.append(s_)
    # 全称句：按原文行号记录，跳过代码块、标题、表格分隔行，以及本来就是疑问的句子（带 ❓ 或"是否"）
    name_ = os.path.basename(f)
    if re.match(r"\d", name_) or name_ == "compare.md":
        univ_dirs.add(os.path.dirname(os.path.abspath(f)))
        deep = name_[:3] in ("03-", "04-") or name_ == "compare.md"
        fence = None
        for no, ln in enumerate(text.split("\n"), 1):
            s_ = ln.strip()
            fm = re.match(r"(```|~~~)", s_)
            if fm:
                fence = None if fence == fm.group(1) else (fence or fm.group(1))
                continue
            if fence or not s_ or s_.startswith("#") or re.fullmatch(r"\|[\s:|-]+\|?", s_) or "❓" in s_ or "是否" in s_:
                continue
            plain = re.sub(r"`[^`]*`", "", re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", ln))
            m_ = UNIVERSAL.search(plain) or (deep and UNIVERSAL_DEEP.search(plain))
            if m_ and not SCOPED.search(plain):
                weak_word = m_.group(0) in ("只有", "完全", "所有", "全部", "不存在")
                rank = (0 if deep else 1, 1 if weak_word else 0)
                universal.append((f, no, re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s_), rank))  # 链接只留文字
    refs_total += n
    bad_total += len(bad)
    print(f"{f}: {n} 条引用，{len(bad)} 条有问题" + (f"，已改写 {len(edits)} 条为永久链接" if edits else ""))
    for x in bad:
        print("   ", x)
    for x in shown:
        print("    ·", x)
    if weak:
        print(f"    提示：{len(weak)} 行标了 ✅ 但本行没有行号级代码引用，也没有写检索 / git 命令作证据，建议补上出处，例如：")
        for ln in weak[:3]:
            print("      ·", ln[:100])
    if strong:
        print(f"    提示：{len(strong)} 处绝对化用语，请确认证据撑得起这么强的说法，撑不起就改弱，例如：")
        for ln in strong[:3]:
            print("      ·", ln[:100])
# 全称句清单：每个目录一份，交付前逐条对照（只提示，不影响退出码）
for out_dir in sorted(univ_dirs):
    path_ = os.path.join(out_dir, "_全称句清单.txt")
    items = [u for u in universal if os.path.dirname(os.path.abspath(u[0])) == out_dir]
    if not items:
        if os.path.isfile(path_):
            try:
                os.remove(path_)
                print(f"提示：{out_dir} 已没有全称句，删掉了旧的 _全称句清单.txt")
            except OSError:
                pass
        continue
    per_file, keep = Counter(), []
    for u in sorted(items, key=lambda x: x[3]):  # 主流程、精读和对比文档在前，强全称词在前
        if per_file[u[0]] < 12 and len(keep) < 60:
            per_file[u[0]] += 1
            keep.append(u)
    try:
        with open(path_, "w", encoding="utf-8") as fh:
            fh.write("全称句清单（checklinks.py 生成）：逐条对照同一章的正文、表格、待确认清单和首屏；"
                     "前后矛盾的改掉，撑不起的写明范围或改弱（见 references/layers.md 常见误判清单）。\n\n")
            for fn, no, ln, _ in keep:
                fh.write(f"{os.path.basename(fn)}:{no}\t{ln[:200]}\n")
            if len(items) > len(keep):
                fh.write(f"\n……另有 {len(items) - len(keep)} 句未列出（每份文档最多 12 句、共 60 句）\n")
        print(f"提示：{len(items)} 句全称说法已列入 {path_}，交付前逐条对照同章正文、表格和待确认清单")
    except OSError as e:
        print(f"提示：{len(items)} 句全称说法，清单写不进 {out_dir}（{e}）")
# 关键结论核对表：首屏结论要从这张表里来（只提示，不影响退出码）
for d in sorted({os.path.dirname(os.path.abspath(f)) for f in files
                 if re.match(r"\d", os.path.basename(f)) and os.path.isfile(f)}):
    idx = os.path.join(d, "index.md")
    if os.path.isfile(idx) and "关键结论核对表" not in open(idx, encoding="utf-8").read():
        print(f"提示：{idx} 还没有「关键结论核对表」：首屏结论和否定、全称、数量等关键判断，"
              "逐条写范围、证据和查过的反例（见 SKILL.md 第 5 节第 8 条）")
# 精读了核心模块，就要说明是谁选的、依据是什么
for d in sorted({os.path.dirname(os.path.abspath(f)) for f in files
                 if os.path.basename(f).startswith("04-") and os.path.isfile(f)}):
    idx = os.path.join(d, "index.md")
    if not os.path.isfile(idx):
        print(f"提示：{d} 下还没有 index.md；写的时候记得写「选题依据」（用户原话、明确委托的原话，或「小仓库，按候选表自选」）")
        continue
    itext = open(idx, encoding="utf-8").read()
    if "等待选题" in itext:
        print(f"{idx}: 写着「等待选题」，却已有核心模块精读（04- 文档）：选定后把选题依据改成用户的原话，或删掉未经选择的精读")
        bad_total += 1
    elif "选题依据" not in itext:
        print(f"{idx}: 有核心模块精读（04- 文档），但没写「选题依据」：大仓库要写用户选择或明确委托的原话，小仓库写「按候选表自选」及理由")
        bad_total += 1
print(f"合计 {refs_total} 条引用，{bad_total} 条有问题" + (f"，已改写 {fixed_total} 条" if fixed_total else "") + NOTE)
sys.exit(1 if bad_total else 0)
