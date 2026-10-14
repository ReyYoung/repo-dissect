"""repo-dissect 版本检查与更新：对比本机安装的版本和 GitHub 上的最新正式版。

用法（只用标准库，Python 3.8+）:
  python3 version_check.py            只检查，列出新版本的主要改动（最多约 10 秒）
  python3 version_check.py --update   更新到最新正式版：只在用户同意后由 Agent 执行，或用户自己执行

check_env.py 开头会自动做检查；设置环境变量 RD_NO_UPDATE_CHECK=1 可关闭检查。
检查本身不会下载或替换任何文件。--update 会：
  - git 克隆安装的：git pull --ff-only；技能目录有本地改动时不更新，先说明改了哪些文件
  - 其他安装方式：下载最新 tag 的代码，核对其中的 VERSION，旧版本备份到 ~/.cache/repo-dissect-backup/ 后覆盖
    SKILL.md、VERSION、agents/、references/、scripts/、assets/
更新完成后要重新读取 SKILL.md（规则可能变了），再重新运行 check_env.py。
退出码：检查 0 已是最新或无法判断，10 有新版本；--update 0 成功，1 失败，3 有本地改动未更新。
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

REPO = "ReyYoung/repo-dissect"
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS = ("SKILL.md", "VERSION", "agents", "references", "scripts", "assets")  # 技能本身的文件，更新时只动这些

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


def local_version(d=SKILL_DIR):
    try:
        with open(os.path.join(d, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def api(path, accept="application/vnd.github+json", timeout=4):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}{path}",
                                 headers={"Accept": accept, "User-Agent": "repo-dissect"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def git_env():
    return dict(os.environ, GIT_TERMINAL_PROMPT="0")


def latest_version(timeout=4):
    """GitHub 上最大的正式版本号（看 tag，不要求建 Release）。先问 API，不通再用 git ls-remote"""
    tags = []
    try:
        tags = [t.get("name", "") for t in json.loads(api("/tags?per_page=100", timeout=timeout).decode("utf-8"))]
    except Exception:
        try:
            r = subprocess.run(["git", "ls-remote", "--tags", f"https://github.com/{REPO}.git"],
                               capture_output=True, timeout=timeout + 4, env=git_env())
            tags = [ln.split("refs/tags/", 1)[1] for ln in r.stdout.decode("utf-8", "replace").splitlines()
                    if "refs/tags/" in ln and not ln.endswith("^{}")]
        except Exception:
            tags = []
    vers = sorted((p, t) for t in tags for p in [parse(t)] if p)
    return (vers[-1][1].lstrip("v") if vers else None)


def changes(local, latest, limit=6):
    """新版本的主要改动：读最新 tag 的 CHANGELOG.zh-CN.md，取比本地新的各版本里的一级条目，每条压成一句"""
    text = None
    for get in (lambda: api(f"/contents/CHANGELOG.zh-CN.md?ref=v{latest}", accept="application/vnd.github.raw"),
                lambda: urllib.request.urlopen(urllib.request.Request(
                    f"https://raw.githubusercontent.com/{REPO}/v{latest}/CHANGELOG.zh-CN.md",
                    headers={"User-Agent": "repo-dissect"}), timeout=4).read()):
        try:
            text = get().decode("utf-8")
            break
        except Exception:
            continue
    if not text:
        return []
    return parse_changes(text, local, limit)


def parse_changes(text, local, limit=6):
    """从 CHANGELOG 里取比 local 新的版本的一级条目，每条压成一句；只是引子（以冒号结尾）的条目，用它下面各条的加粗标题"""
    lp = parse(local) or (0, 0, 0)
    items, keep = [], False

    def short(t):
        b = re.match(r"\*\*(.+?)\*\*\s*(.*)", t)
        if b:
            head = re.sub(r"`", "", b.group(1)).strip().rstrip("。.：:")
            if len(head) <= 4 and b.group(2):  # 标题太短（如"数字"），补上后面半句
                head += "：" + re.split(r"[。；，,]", re.sub(r"[`*]", "", b.group(2)))[0].strip()
            return head
        return re.split(r"[。；:：]", re.sub(r"[`*]", "", t))[0].strip().rstrip("。.：:")

    for ln in text.splitlines():
        m = re.match(r"## \[(\d+\.\d+\.\d+)\]", ln)
        if m:
            keep = (parse(m.group(1)) or (0, 0, 0)) > lp
            continue
        if not keep:
            continue
        if ln.startswith("- "):
            items.append([ln[2:].strip(), []])
        elif re.match(r"\s{2,}- ", ln) and items:
            items[-1][1].append(short(ln.strip()[2:]))
    out = []
    for head, subs in items:
        intro = not head.startswith("**") and re.sub(r"[`*]", "", head).rstrip().endswith(("：", ":"))
        t = (short(head) + "：" + "、".join(subs[:4])) if intro and subs else short(head)
        out.append(t if len(t) <= 48 else t[:46] + "…")
    return out[:limit]


def git_state(d=SKILL_DIR):
    """技能目录是 git 克隆时返回 (True, 本地改动的文件列表)；否则 (False, [])"""
    if not os.path.isdir(os.path.join(d, ".git")):
        return False, []
    try:
        r = subprocess.run(["git", "-C", d, "status", "--porcelain"], capture_output=True, timeout=5)
        return True, [ln[3:] for ln in r.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]
    except Exception:
        return True, []


def update_cmd():
    py = sys.executable or "python3"
    return f'"{py}" "{os.path.join(SKILL_DIR, "scripts", "version_check.py")}" --update'


def check():
    """返回 dict: local, latest, newer(bool|None), changes(list), advice(list[str])"""
    local = local_version()
    if os.environ.get("RD_NO_UPDATE_CHECK"):
        return {"local": local, "latest": None, "newer": None, "changes": [], "advice": [], "skipped": True}
    latest = latest_version()
    lp, rp = parse(local), parse(latest)
    newer = (rp > lp) if (lp and rp) else (True if (rp and not local) else None)
    advice, chg = [], []
    is_git, dirty = git_state()
    if newer:
        chg = changes(local, latest)
        if chg:
            advice.append(f"{latest} 的主要改动：" + "；".join(chg))
        if dirty:
            advice.append(f"技能目录里有 {len(dirty)} 个文件被改过（{'、'.join(dirty[:3])}{' 等' if len(dirty) > 3 else ''}，"
                          "可能是 Agent 在拆解时改的）：更新前请用户决定保留还是还原，--update 不会覆盖它们")
        advice.append(f"用户同意更新后执行：{update_cmd()}；完成后重新读取 SKILL.md，再运行 check_env.py")
        advice.append(f"完整更新记录：https://github.com/{REPO}/blob/main/CHANGELOG.zh-CN.md")
    elif dirty:
        advice.append(f"技能目录里有 {len(dirty)} 个文件被改过，和发布版不一致；拆解时请不要修改技能自身的文件，"
                      "发现脚本问题记进 index.md 反馈给作者")
    return {"local": local, "latest": latest, "newer": newer, "changes": chg, "advice": advice, "skipped": False}


def summary(res):
    """一行结论，给 check_env.py 用"""
    loc = res["local"] or "未知（1.3.0 及更早版本没有 VERSION 文件）"
    if res.get("skipped"):
        return f"{loc}（已按 RD_NO_UPDATE_CHECK 跳过更新检查）"
    if res["newer"]:
        return f"{loc}，GitHub 上已有 {res['latest']}"
    if res["latest"] is None:
        return f"{loc}（查不到 GitHub 上的最新版本，已跳过）"
    return f"{loc}，已是最新"


# ---------------------------------------------------------------- 更新
def fetch_release(tag, dest):
    """把 tag 对应的代码取到 dest：先 git clone（会用环境里的代理），不行再下载整包"""
    try:
        r = subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", tag,
                            f"https://github.com/{REPO}.git", dest], capture_output=True, timeout=180, env=git_env())
        if r.returncode == 0:
            return True, "git clone"
        err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:]
    except Exception as e:
        err = [f"{type(e).__name__}: {e}"]
    try:
        shutil.rmtree(dest, ignore_errors=True)
        req = urllib.request.Request(f"https://codeload.github.com/{REPO}/tar.gz/refs/tags/{tag}",
                                     headers={"User-Agent": "repo-dissect"})
        with urllib.request.urlopen(req, timeout=120) as r, tempfile.TemporaryFile() as tf:
            shutil.copyfileobj(r, tf)
            tf.seek(0)
            with tarfile.open(fileobj=tf, mode="r:gz") as t:
                os.makedirs(dest)
                for m in t.getmembers():
                    parts = m.name.split("/", 1)
                    if len(parts) < 2 or not parts[1] or ".." in parts[1].split("/") or parts[1].startswith("/"):
                        continue
                    if not (m.isfile() or m.isdir()):
                        continue  # 不解出符号链接、设备文件
                    m.name = parts[1]
                    t.extract(m, dest, **({"filter": "data"} if hasattr(tarfile, "data_filter") else {}))
        return True, "整包下载"
    except Exception as e:
        return False, f"git clone 失败（{'；'.join(err)}），整包下载也失败（{type(e).__name__}）"


def do_update():
    res = check()
    if not res["newer"]:
        print("repo-dissect 版本: " + summary(res) + "，不需要更新")
        return 0
    latest, local = res["latest"], res["local"]
    is_git, dirty = git_state()
    if dirty:
        print(f"没有更新：技能目录 {SKILL_DIR} 里有 {len(dirty)} 个文件被改过：")
        for f in dirty[:10]:
            print("  -", f)
        print(f"请用户决定：不需要这些改动就执行 git -C \"{SKILL_DIR}\" checkout -- . 还原后再更新；需要就先备份")
        return 3
    if is_git:
        r = subprocess.run(["git", "-C", SKILL_DIR, "pull", "--ff-only", "--quiet"], capture_output=True,
                           timeout=180, env=git_env())
        if r.returncode != 0:
            print("更新失败：git pull 没成功：" + (r.stderr or b"").decode("utf-8", "replace").strip()[-300:])
            print(f"可以在浏览器打开 https://github.com/{REPO} 按 README 重新安装")
            return 1
        how = "git pull"
    else:
        tmp = tempfile.mkdtemp(prefix="rd-update-")
        try:
            new = os.path.join(tmp, "new")
            ok, how = fetch_release(f"v{latest}", new)
            if not ok:
                print("更新失败：" + how)
                print(f"可以在浏览器打开 https://github.com/{REPO} 下载后按 README 手动安装")
                return 1
            got = local_version(new)
            if got != latest or not os.path.isfile(os.path.join(new, "SKILL.md")):
                print(f"更新失败：下载到的代码版本是 {got}，不是 {latest}，没有替换任何文件")
                return 1
            backup = os.path.join(os.path.expanduser("~"), ".cache", "repo-dissect-backup",
                                  f"{local or 'old'}-{time.strftime('%Y%m%d-%H%M%S')}")
            os.makedirs(backup)
            for p in PARTS:  # 先完整备份，再逐项替换
                src = os.path.join(SKILL_DIR, p)
                if os.path.isdir(src):
                    shutil.copytree(src, os.path.join(backup, p), ignore=shutil.ignore_patterns("__pycache__"))
                elif os.path.isfile(src):
                    shutil.copy2(src, os.path.join(backup, p))
            def put(frm):
                for p in PARTS:
                    src, dst = os.path.join(frm, p), os.path.join(SKILL_DIR, p)
                    if not os.path.exists(src):
                        continue
                    if os.path.isdir(dst):
                        shutil.rmtree(dst)
                    elif os.path.isfile(dst):
                        os.remove(dst)
                    shutil.copytree(src, dst) if os.path.isdir(src) else shutil.copy2(src, dst)
            try:
                put(new)
            except Exception as e:  # 替换到一半失败（文件被占用、只读等）：用备份还原
                try:
                    put(backup)
                    print(f"更新失败（{type(e).__name__}: {e}），已从备份还原旧版本")
                except Exception as e2:
                    print(f"更新失败（{type(e).__name__}: {e}），从备份还原也失败（{e2}）：请把 {backup} 里的文件手动复制回 {SKILL_DIR}")
                return 1
            print(f"旧版本已备份到 {backup}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    now = local_version()
    if now != latest:
        print(f"更新后的版本是 {now}，不是预期的 {latest}，请检查 {SKILL_DIR}")
        return 1
    print(f"已更新：{local or '旧版本'} → {now}（{how}）。请重新读取 {os.path.join(SKILL_DIR, 'SKILL.md')}，"
          "再运行 check_env.py，按新版本的规则开工")
    return 0


def main():
    if "--update" in sys.argv[1:]:
        return do_update()
    res = check()
    print("repo-dissect 版本: " + summary(res))
    for a in res["advice"]:
        print("  -", a)
    return 10 if res["newer"] else 0


if __name__ == "__main__":
    sys.exit(main())
