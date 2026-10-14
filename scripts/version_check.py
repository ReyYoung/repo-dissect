"""repo-dissect 版本检查：对比本机安装的版本和 GitHub 上的最新正式版，有新版本时给出更新方法。

用法: python3 version_check.py            （只用标准库，Python 3.8+，最多约 8 秒）
      check_env.py 会自动调用它；设置环境变量 RD_NO_UPDATE_CHECK=1 可关闭。

只检查和提醒，不会自动下载或替换任何文件：技能里的脚本会在用户电脑上执行，更新与否由用户决定。
查不到（没网、被限流）时安静跳过，不影响拆解。
退出码: 0 已是最新或无法判断；10 有新版本。
"""
import json
import os
import re
import subprocess
import sys
import urllib.request

REPO = "ReyYoung/repo-dissect"
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def parse(v):
    """'v1.3.0' / '1.3.0' → (1, 3, 0)；预发布（带 - 的）和不规范的返回 None"""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def local_version():
    try:
        with open(os.path.join(SKILL_DIR, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def latest_version(timeout=4):
    """GitHub 上最大的正式版本号（看 tag，不要求建 Release）。先问 API，不通再用 git ls-remote"""
    tags = []
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/tags?per_page=100",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "repo-dissect"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            tags = [t.get("name", "") for t in json.loads(r.read().decode("utf-8"))]
    except Exception:
        try:
            r = subprocess.run(["git", "ls-remote", "--tags", f"https://github.com/{REPO}.git"],
                               capture_output=True, timeout=timeout,
                               env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
            tags = [ln.split("refs/tags/", 1)[1] for ln in r.stdout.decode("utf-8", "replace").splitlines()
                    if "refs/tags/" in ln and not ln.endswith("^{}")]
        except Exception:
            tags = []
    vers = sorted((p, t) for t in tags for p in [parse(t)] if p)
    return (vers[-1][1].lstrip("v") if vers else None)


def git_state():
    """技能目录是 git 克隆时返回 (True, 本地改动的文件数)；否则 (False, 0)"""
    if not os.path.isdir(os.path.join(SKILL_DIR, ".git")):
        return False, 0
    try:
        r = subprocess.run(["git", "-C", SKILL_DIR, "status", "--porcelain"], capture_output=True, timeout=5)
        return True, len([ln for ln in r.stdout.decode("utf-8", "replace").splitlines() if ln.strip()])
    except Exception:
        return True, 0


def check():
    """返回 dict: local, latest, newer(bool|None), advice(list[str])"""
    local = local_version()
    if os.environ.get("RD_NO_UPDATE_CHECK"):
        return {"local": local, "latest": None, "newer": None, "advice": [], "skipped": True}
    latest = latest_version()
    lp, rp = parse(local), parse(latest)
    newer = (rp > lp) if (lp and rp) else (True if (rp and not local) else None)
    advice = []
    is_git, dirty = git_state()
    if newer:
        if is_git:
            if dirty:
                advice.append(f"技能目录里有 {dirty} 个文件被改过（可能是 Agent 在拆解时改的），更新前先看 "
                              f"git -C \"{SKILL_DIR}\" status，需要的改动先备份")
            advice.append(f"更新：git -C \"{SKILL_DIR}\" pull --ff-only")
        else:
            advice.append(f"更新：在 Agent 对话框里发「从 https://github.com/{REPO} 更新 repo-dissect 技能到最新版，"
                          f"覆盖安装到 {SKILL_DIR}，然后运行 scripts/check_env.py 校验」")
        advice.append(f"更新内容见 https://github.com/{REPO}/blob/main/CHANGELOG.zh-CN.md")
    elif is_git and dirty:
        advice.append(f"技能目录里有 {dirty} 个文件被改过，和发布版不一致；拆解时请不要修改技能自身的文件，"
                      f"发现脚本问题记进 index.md 反馈给作者")
    return {"local": local, "latest": latest, "newer": newer, "advice": advice, "skipped": False}


def summary(res):
    """一行结论，给 check_env.py 用"""
    loc = res["local"] or "未知（1.3.0 及更早版本没有 VERSION 文件）"
    if res.get("skipped"):
        return f"{loc}（已按 RD_NO_UPDATE_CHECK 跳过更新检查）"
    if res["newer"]:
        return f"{loc}，GitHub 上已有 {res['latest']}，建议更新"
    if res["latest"] is None:
        return f"{loc}（查不到 GitHub 上的最新版本，已跳过）"
    return f"{loc}，已是最新"


def main():
    res = check()
    print("repo-dissect 版本: " + summary(res))
    for a in res["advice"]:
        print("  -", a)
    return 10 if res["newer"] else 0


if __name__ == "__main__":
    sys.exit(main())
