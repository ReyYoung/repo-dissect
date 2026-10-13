"""核验文档里的代码引用（只用标准库，Python 3.8+）。

用法:
  python3 checklinks.py <src目录> <owner/repo> <sha> 文件1.md [文件2.md ...]        # GitHub 项目
  python3 checklinks.py <src目录> local <sha> 文件1.md ...                          # 本地仓库
  加 --fix：把 GitHub 项目里写成本地路径的引用（如 `api/app.py:12-30`）改写成固定 commit 的永久链接

核验内容:
  1. 永久链接 https://github.com/<owner/repo>/blob/<sha>/<path>#L10-L20：commit 必须是本次固定的 sha，
     文件在该 commit 下存在，行号不越界
  2. 本地路径写法 `path:10`、`path:10-20`、`path:L10-L20`：同样核验文件和行号；
     路径不完整（如只写文件名）时，若在仓库里唯一匹配就按完整路径核验并提示补全
  3. GitHub 项目里出现本地路径写法 → 报"未写成永久链接"（可用 --fix 自动改写）
  4. 编号开头的分层文档（00-、01-……）一条代码引用都没有 → 报错，不能算核验通过
  5. 占位引用 → 报错：单行引用指向空行、只有括号的行，或文件第 1 行的 import / package / {
     这类文件开头内容——它们只能说明"文件在这"，证明不了结论；请改指到真正证明结论的行
  6. 提示（不影响退出码）：标了 ✅ 的行里没有行号级代码引用，列出前几处供补证据
对比模式下对每个仓库各运行一次（compare.md 每次都带上）。发现问题时退出码为 1。
"""
import re
import subprocess
import sys
from urllib.parse import unquote

args = sys.argv[1:]
FIX = "--fix" in args
args = [a for a in args if a != "--fix"]
if len(args) < 4:
    sys.exit(__doc__)
src, repo, sha, files = args[0], args[1], args[2], args[3:]
LOCAL = repo == "local"
if not re.fullmatch(r"[0-9a-f]{40}", sha):
    sys.exit(f"<sha> 需要 40 位完整 commit 号，现在是 {sha!r}；用 git -C <src> rev-parse HEAD 获取")
if FIX and LOCAL:
    sys.exit("--fix 只用于 GitHub 项目（本地仓库本来就用 path:行号 写法）")

r = subprocess.run(["git", "-C", src, "ls-tree", "-r", "--name-only", sha], capture_output=True, text=True)
if r.returncode:
    sys.exit(f"读取 {src} 在 {sha[:12]} 的文件列表失败：{r.stderr.strip()[:200]}")
TREE = set(r.stdout.splitlines())
BY_NAME = {}
for p in TREE:
    BY_NAME.setdefault(p.rsplit("/", 1)[-1], []).append(p)

PERMA = re.compile(r"https://github\.com/" + (re.escape(repo) if not LOCAL else r"[^/\s]+/[^/\s]+")
                   + r"/blob/([^/\s)]+)/([^)#\s`]+)(?:#L(\d+)(?:-L(\d+))?)?")
# `path:10` / `path:10-20` / `path:L10-L20`，写在反引号里；路径要有字母开头的扩展名
LOCALREF = re.compile(r"(?<!\[)`([A-Za-z0-9_.@+\-/]+\.[A-Za-z][A-Za-z0-9]*):L?(\d+)(?:\s*[-–]\s*L?(\d+))?`")
FENCE = re.compile(r"^```.*?^```", re.S | re.M)
cache = {}
# 不能当证据的行：空行、只有括号/标点；以及文件第 1 行的 import、package、shebang 等文件开头内容
TRIVIAL = re.compile(r"^\s*[{}\[\]();,]*\s*$")
HEADER = re.compile(r"^\s*(import\s|from\s+\S+\s+import\s|package\s|use\s|require\(|#include|#!|<\?xml|['\"]use strict['\"])")


def file_lines(path):
    if path not in cache:
        rr = subprocess.run(["git", "-C", src, "show", f"{sha}:{path}"], capture_output=True)
        cache[path] = None if rr.returncode else rr.stdout.decode("utf-8", "replace").split("\n")
        if cache[path] and cache[path][-1] == "":
            cache[path].pop()
    return cache[path]


def nlines(path):
    ls = file_lines(path)
    return None if ls is None else len(ls)


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
    path = path.lstrip("./")
    if path in TREE:
        return path, ""
    hits = sorted(p for p in TREE if p.endswith("/" + path)) if "/" in path else sorted(BY_NAME.get(path, []))
    if len(hits) == 1:
        return hits[0], f"路径不完整，应为 {hits[0]}"
    if len(hits) > 1:
        return None, f"路径不完整且有 {len(hits)} 个同名文件（如 {hits[0]}），请写完整路径"
    return None, "文件不存在"


def check_lines(full, a, b):
    total = nlines(full)
    a, b = int(a), int(b or a)
    if b < a:
        return f"行号范围颠倒 L{a}-L{b}"
    if b > total:
        return f"行号越界 L{a}{'-L' + str(b) if b != a else ''}（文件共 {total} 行）"
    return ""


bad_total = refs_total = fixed_total = 0
for f in files:
    try:
        text = open(f, encoding="utf-8").read()
    except FileNotFoundError:
        print(f"{f}: 文件不存在，跳过")
        continue
    body = FENCE.sub(lambda m: " " * len(m.group(0)), text)  # 代码块里的不算引用
    bad, n = [], 0
    for m in PERMA.finditer(body):
        n += 1
        s, path, a, b = m.groups()
        path = unquote(path)
        if s != sha:
            bad.append(f"commit 不是本次固定的 {sha[:12]}（写成了 {s[:12]}）: {path}")
        elif path not in TREE:
            bad.append(f"文件不存在: {path}")
        elif a:
            msg = check_lines(path, a, b) or placeholder(path, a, b)
            if msg:
                bad.append(f"{msg}: {path}#L{a}")
    edits = []
    for m in LOCALREF.finditer(body):
        n += 1
        path, a, b = m.groups()
        full, hint = resolve(path)
        where = f"`{path}:{a}{'-' + b if b else ''}`"
        if not full:
            bad.append(f"{hint}: {where}")
            continue
        msg = check_lines(full, a, b) or placeholder(full, a, b)
        if msg:
            bad.append(f"{msg}: {where}")
            continue
        if not LOCAL:
            if FIX:
                rng = f"L{a}" + (f"-L{b}" if b and b != a else "")
                edits.append((m.start(), m.end(), f"[{full}:{rng}](https://github.com/{repo}/blob/{sha}/{full}#{rng})"))
            else:
                bad.append(f"未写成永久链接（可加 --fix 自动改写）: {where}" + (f"；{hint}" if hint else ""))
        elif hint:
            bad.append(f"{hint}: {where}")
    if edits:
        for s0, e0, new in sorted(edits, reverse=True):
            text = text[:s0] + new + text[e0:]
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(text)
        fixed_total += len(edits)
    # ✅ = 代码事实，应能对到代码行；只提示，不计入问题
    weak = [ln.strip() for ln in body.split("\n")
            if "✅" in ln and not ("🔍" in ln and "❓" in ln) and not PERMA.search(ln) and not LOCALREF.search(ln)]
    name = f.replace("\\", "/").rsplit("/", 1)[-1]
    if n == 0 and re.match(r"\d", name):
        bad.append("没有任何代码引用：分层文档的结论必须对到代码位置（固定 commit 的永久链接或 path:行号）")
    refs_total += n
    bad_total += len(bad)
    print(f"{f}: {n} 条引用，{len(bad)} 条有问题" + (f"，已改写 {len(edits)} 条为永久链接" if edits else ""))
    for x in bad:
        print("   ", x)
    if weak:
        print(f"    提示：{len(weak)} 行标了 ✅ 但本行没有行号级代码引用（检索命令、无命中类证据可忽略），其余建议补上出处，例如：")
        for ln in weak[:3]:
            print("      ·", ln[:100])
print(f"合计 {refs_total} 条引用，{bad_total} 条有问题" + (f"，已改写 {fixed_total} 条" if fixed_total else ""))
sys.exit(1 if bad_total else 0)
