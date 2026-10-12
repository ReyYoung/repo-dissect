"""核验永久链接：文件在该 commit 下存在、行号不超出文件长度（只用标准库，Python 3.8+）。

用法: python3 checklinks.py <src目录> <owner/repo> <sha> 文件1.md [文件2.md ...]
只检查指向 <owner/repo> 的链接；对比模式下对每个仓库各运行一次（compare.md 可以每次都带上）。
发现问题时退出码为 1。
"""
import re
import subprocess
import sys
from urllib.parse import unquote

if len(sys.argv) < 5:
    sys.exit(__doc__)
src, repo, sha, files = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
if not re.fullmatch(r"[0-9a-f]{40}", sha):
    sys.exit(f"<sha> 需要 40 位完整 commit 号，现在是 {sha!r}；用 git -C <src> rev-parse HEAD 获取")
pat = re.compile(rf"https://github\.com/{re.escape(repo)}/blob/([^/\s)]+)/([^)#\s`]+)(?:#L(\d+)(?:-L(\d+))?)?")
cache = {}


def nlines(path):
    if path not in cache:
        r = subprocess.run(["git", "-C", src, "show", f"{sha}:{path}"], capture_output=True)
        cache[path] = None if r.returncode else r.stdout.count(b"\n") + (0 if r.stdout.endswith(b"\n") else 1)
    return cache[path]


bad_total = 0
for f in files:
    try:
        text = open(f, encoding="utf-8").read()
    except FileNotFoundError:
        print(f"{f}: 文件不存在，跳过")
        continue
    bad, n = [], 0
    for m in pat.finditer(text):
        n += 1
        s, path, a, b = m.groups()
        path = unquote(path)
        if s != sha:
            bad.append(f"commit 不是本次固定的 {sha[:12]}（写成了 {s}）: {path}")
            continue
        total = nlines(path)
        if total is None:
            bad.append(f"文件不存在: {path}")
        elif int(b or a or 0) > total:
            bad.append(f"行号越界: {path}#L{a}{'-L' + b if b else ''}（文件共 {total} 行）")
        elif a and b and int(b) < int(a):
            bad.append(f"行号范围颠倒: {path}#L{a}-L{b}")
    bad_total += len(bad)
    print(f"{f}: {n} 条链接，{len(bad)} 条有问题")
    for x in bad:
        print("   ", x)
sys.exit(1 if bad_total else 0)
