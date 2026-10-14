"""repo-dissect 版本检查与更新：对比本机安装的版本和 GitHub 上的最新正式版。

用法（只用标准库，Python 3.8+）:
  python3 version_check.py            只检查，列出新版本的主要改动；查不到时自动换直连、本机代理各再试一次
  python3 version_check.py --update   更新到最新正式版：只在用户同意后由 Agent 执行，或用户自己执行
  可加 --proxy URL|none：只对本次命令指定代理或强制直连

check_env.py 开头会自动做检查；设置环境变量 RD_NO_UPDATE_CHECK=1 可关闭检查。
检查本身不会下载或替换任何文件。--update 会：
  - git 克隆安装的：git pull --ff-only；技能目录有本地改动时不更新，先说明改了哪些文件
  - 其他安装方式：下载最新 tag 的代码，核对其中的 VERSION，旧版本备份到 ~/.cache/repo-dissect-backup/ 后覆盖
    SKILL.md、VERSION、agents/、references/、scripts/、assets/
更新完成后要重新读取 SKILL.md（规则可能变了），再重新运行 check_env.py。
退出码：检查 0 已是最新（或按 RD_NO_UPDATE_CHECK 跳过），10 有新版本，20 查不到最新版本（状态未知，不等于已是最新）；
        --update 0 成功，1 失败，3 有本地改动未更新。
查不到时会在 ~/.cache/repo-dissect/version-check.json 记一笔，fetch_repo.py 取码成功后据此自动复查一次。
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

sys.dont_write_bytecode = True  # 不在技能目录里生成 __pycache__（运行时不改技能自己的文件）
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


PROXY_ENV = ("https_proxy", "HTTPS_PROXY", "http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY")
STATE = os.path.join(os.path.expanduser("~"), ".cache", "repo-dissect", "version-check.json")


def opener(proxy=None):
    """proxy=None 按环境变量（系统默认）；"" 强制直连；URL 只对本次请求用这个代理"""
    if proxy is None:
        return urllib.request.build_opener()
    return urllib.request.build_opener(urllib.request.ProxyHandler({"https": proxy, "http": proxy} if proxy else {}))


def api(path, accept="application/vnd.github+json", timeout=5, proxy=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}{path}",
                                 headers={"Accept": accept, "User-Agent": "repo-dissect"})
    with opener(proxy).open(req, timeout=timeout) as r:
        return r.read()


def git_env(proxy=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    if proxy is not None:  # 指定了路线：去掉环境变量里的代理，只用指定的
        for k in PROXY_ENV:
            env.pop(k, None)
        if proxy:
            env["HTTPS_PROXY"] = env["HTTP_PROXY"] = proxy
    return env


def _fr():
    """同目录的 fetch_repo.py（探测本机代理、读 git 代理配置）；导入失败返回 None"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import fetch_repo
        return fetch_repo
    except Exception:
        return None


def git_cmd(proxy=None):
    """只对本条命令生效的代理设置，不改用户的 git 配置。指定了路线时，http.proxy 和针对 GitHub 的
    http.<url>.proxy 都要覆盖（后者优先级更高，只覆盖前者绕不开失效的代理）"""
    if proxy is None:
        return ["git"]
    cmd = ["git", "-c", f"http.proxy={proxy}"]
    fr = _fr()
    try:
        keys = fr.git_proxy_keys() if fr else []
    except Exception:
        keys = []
    for k, _ in keys:
        if k.lower() != "http.proxy":
            cmd += ["-c", f"{k}={proxy}"]
    return cmd


def brief(e):
    if isinstance(e, subprocess.TimeoutExpired):
        return "超时"
    why = getattr(e, "reason", None) or e  # URLError 只取原因
    if isinstance(why, socket.timeout) or "timed out" in str(why):
        return "超时"
    return f"{type(why).__name__ if isinstance(why, Exception) else type(e).__name__}: {why}"[:80]


def latest_version(timeout=5, proxy=None):
    """GitHub 上最大的正式版本号（看 tag，不要求建 Release）。先问 API，不通再用 git ls-remote。
    返回 (版本或 None, 失败原因)"""
    tags, errs = None, []
    try:
        tags = [t.get("name", "") for t in json.loads(api("/tags?per_page=100", timeout=timeout, proxy=proxy).decode("utf-8"))]
    except Exception as e:
        errs.append("API " + brief(e))
        try:
            r = subprocess.run(git_cmd(proxy) + ["ls-remote", "--tags", f"https://github.com/{REPO}.git"],
                               capture_output=True, timeout=timeout + 4, env=git_env(proxy))
            if r.returncode == 0:
                tags = [ln.split("refs/tags/", 1)[1] for ln in r.stdout.decode("utf-8", "replace").splitlines()
                        if "refs/tags/" in ln and not ln.endswith("^{}")]
            else:
                last = ((r.stderr or b"").decode("utf-8", "replace").strip().splitlines() or ["失败"])[-1]
                errs.append("git " + re.sub(r"^fatal: unable to access '[^']*': ", "", last)[:80])
        except Exception as e2:
            errs.append("git " + brief(e2))
    if tags is None:
        return None, "；".join(errs)
    vers = sorted((p, t) for t in tags for p in [parse(t)] if p)
    return (vers[-1][1].lstrip("v"), "") if vers else (None, "没有找到正式版本的 tag")


def changes(local, latest, limit=6, proxy=None):
    """新版本的主要改动：读最新 tag 的 CHANGELOG.zh-CN.md，取比本地新的各版本里的一级条目，每条压成一句"""
    text = None
    for get in (lambda: api(f"/contents/CHANGELOG.zh-CN.md?ref=v{latest}", accept="application/vnd.github.raw", proxy=proxy),
                lambda: opener(proxy).open(urllib.request.Request(
                    f"https://raw.githubusercontent.com/{REPO}/v{latest}/CHANGELOG.zh-CN.md",
                    headers={"User-Agent": "repo-dissect"}), timeout=5).read()):
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


def update_cmd(proxy=None):
    """更新命令；检查时走通的是指定路线（本机代理或直连），更新也走同一条。
    走的是环境变量里的代理、或代理地址带账号密码时不写进命令（默认就会用环境变量；也避免口令进记录）"""
    py = sys.executable or "python3"
    fr = _fr()
    envp = fr.env_proxy() if fr else None
    if proxy is None or (proxy and (proxy == envp or "@" in proxy)):
        route = ""
    else:
        route = f" --proxy {proxy}" if proxy else " --proxy none"
    return f'"{py}" "{os.path.join(SKILL_DIR, "scripts", "version_check.py")}" --update{route}'


def check_cmd():
    py = sys.executable or "python3"
    return f'"{py}" "{os.path.join(SKILL_DIR, "scripts", "version_check.py")}"'


def other_routes(tried):
    """首次查询失败后再试的路线：直连（绕开可能失效的代理设置）、本机代理端口。各试一次"""
    routes = []
    fr = _fr()
    if not fr:
        return routes
    try:
        configured = fr.env_proxy() or (shutil.which("git") and fr.git_proxy_config())
        if "" not in tried and (configured or any(tried)):  # 只有原来走的不是直连时，直连才算另一条路线
            routes.append("")
        routes += [u for u, _ in fr.local_proxies() if u not in tried]
    except Exception:
        pass
    return routes


def route_name(proxy):
    if proxy is None:
        return "系统默认网络设置"
    return "直连" if proxy == "" else "代理 " + re.sub(r"//[^@/]*@", "//***@", proxy)  # 不打印代理的账号密码


def save_state(res, rechecked=False):
    """写到临时文件再替换，避免别的进程读到写了一半的文件；家目录不可写时静默跳过"""
    try:
        d = os.path.dirname(STATE)
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".vc-", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"status": res["status"], "local": res["local"], "latest": res["latest"],
                       "error": res.get("error", ""), "ts": time.time(), "rechecked": rechecked}, f, ensure_ascii=False)
        os.replace(tmp, STATE)
    except Exception:
        pass


def pending_recheck(max_age=12 * 3600):
    """开工时查不到、还没复查过、且不太久的记录"""
    try:
        with open(STATE, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        return False
    return st.get("status") == "unknown" and not st.get("rechecked") and time.time() - st.get("ts", 0) <= max_age


def check(proxy=None, retry=True, persist=True, offline=None, recheck=False):
    """返回 dict: status(newer/latest/unknown/skipped), local, latest, newer, changes, advice, error, proxy。
    proxy 见 opener()；retry=True 时首次失败再换路线各试一次；persist=True 时把结果记到 STATE。
    offline: 调用方已确认连不上 GitHub 时传原因，直接记为查不到，不再联网；recheck=True 表示这次就是复查"""
    local = local_version()
    if os.environ.get("RD_NO_UPDATE_CHECK"):
        return {"status": "skipped", "local": local, "latest": None, "newer": None, "changes": [], "advice": [],
                "error": "", "proxy": proxy, "skipped": True}
    if offline:
        latest, err, retry = None, offline, False
    else:
        latest, err = latest_version(proxy=proxy)
    tried = [] if offline else [route_name(proxy)]
    if latest is None and retry:
        for px in other_routes([proxy]):
            got, e2 = latest_version(proxy=px)
            tried.append(route_name(px))
            if got:
                latest, proxy, err = got, px, ""
                break
    lp, rp = parse(local), parse(latest)
    newer = (rp > lp) if (lp and rp) else (True if (rp and not local) else None)
    status = "newer" if newer else ("latest" if latest else "unknown")
    if status == "unknown" and tried:
        err = "；".join(x for x in (err, "试过：" + "、".join(tried)) if x)
    advice, chg = [], []
    is_git, dirty = git_state()
    if newer:
        chg = changes(local, latest, proxy=proxy)
        if chg:
            advice.append(f"{latest} 的主要改动：" + "；".join(chg))
        if dirty:
            advice.append(f"技能目录里有 {len(dirty)} 个文件被改过（{'、'.join(dirty[:3])}{' 等' if len(dirty) > 3 else ''}，"
                          "可能是 Agent 在拆解时改的）：更新前请用户决定保留还是还原，--update 不会覆盖它们")
        advice.append(f"用户同意更新后执行：{update_cmd(proxy)}；完成后重新读取 SKILL.md，再运行 check_env.py")
        advice.append(f"完整更新记录：https://github.com/{REPO}/blob/main/CHANGELOG.zh-CN.md")
    elif status == "unknown" and recheck:
        advice.append(f"这是复查，仍查不到：不再重试，本次继续用 {local or '当前版本'}，在 index.md 记下\"版本检查失败、复查仍失败\"")
    elif status == "unknown":
        advice.append(f"查不到最新版本不等于已是最新：开工时告诉用户本地版本 {local or '未知'}、最新版本未知、本次继续用当前版本；"
                      f"取码成功后复查一次（fetch_repo.py 会自动复查；用 git clone 取码、或没看到\"技能版本复查\"一行的，"
                      f"手动执行 {check_cmd()}），只复查一次")
    elif dirty:
        advice.append(f"技能目录里有 {len(dirty)} 个文件被改过，和发布版不一致；拆解时请不要修改技能自身的文件，"
                      "发现脚本问题记进 index.md 反馈给作者")
    res = {"status": status, "local": local, "latest": latest, "newer": newer, "changes": chg, "advice": advice,
           "error": err if status == "unknown" else "", "proxy": proxy, "skipped": False}
    if persist:
        save_state(res, rechecked=recheck)
    return res


def summary(res):
    """一行结论，给 check_env.py 用"""
    loc = res["local"] or "未知（1.3.0 及更早版本没有 VERSION 文件）"
    st = res.get("status")
    if st == "skipped":
        return f"{loc}（已按 RD_NO_UPDATE_CHECK 跳过更新检查）"
    if st == "newer":
        return f"{loc}，GitHub 上已有 {res['latest']}"
    if st == "unknown":
        return f"{loc}；GitHub 上的最新版本查不到（{res.get('error') or '原因不明'}），状态未知"
    via = f"（经{route_name(res['proxy'])} 查询）" if res.get("proxy") is not None else ""
    return f"{loc}，已是最新{via}"


def recheck_pending(proxy=None, max_age=12 * 3600):
    """开工时查不到最新版本、且还没复查过时，复查一次（fetch_repo.py 取码成功后调用）。
    返回要打印的一行；不需要复查时返回 None"""
    if os.environ.get("RD_NO_UPDATE_CHECK") or not pending_recheck(max_age):
        return None
    res = check(proxy=proxy, retry=False, recheck=True)
    if res["status"] == "newer":
        return (f"技能版本复查: 开工时查不到，现在查到 GitHub 上已有 {res['latest']}（当前 {res['local']}）。"
                f"告诉用户并问要不要更新" + (f"（主要改动：{'；'.join(res['changes'][:4])}）" if res["changes"] else "")
                + f"；同意就执行 {update_cmd(res['proxy'])}，成功后重新读取 SKILL.md 再接着做（已取的代码不用重取）；"
                  "不同意、没回复或无人值守就继续用当前版本。在 index.md 记下复查结果")
    if res["status"] == "latest":
        return f"技能版本复查: 开工时查不到，现在确认 {res['local']} 已是最新。在 index.md 记下复查结果"
    return (f"技能版本复查: 仍查不到最新版本（{res['error']}），不再重试；本次继续用 {res['local'] or '当前版本'}，"
            "在 index.md 记下\"版本检查失败、复查仍失败\"")


# ---------------------------------------------------------------- 更新
def fetch_release(tag, dest, proxy=None):
    """把 tag 对应的代码取到 dest：先 git clone，不行再下载整包；proxy 用检查时走通的那条路线"""
    try:
        r = subprocess.run(git_cmd(proxy) + ["clone", "--quiet", "--depth", "1", "--branch", tag,
                            f"https://github.com/{REPO}.git", dest], capture_output=True, timeout=180, env=git_env(proxy))
        if r.returncode == 0:
            return True, "git clone"
        err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:]
    except Exception as e:
        err = [f"{type(e).__name__}: {e}"]
    try:
        shutil.rmtree(dest, ignore_errors=True)
        req = urllib.request.Request(f"https://codeload.github.com/{REPO}/tar.gz/refs/tags/{tag}",
                                     headers={"User-Agent": "repo-dissect"})
        with opener(proxy).open(req, timeout=120) as r, tempfile.TemporaryFile() as tf:
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


def do_update(proxy=None):
    res = check(proxy=proxy, persist=False)
    if res["status"] == "unknown":
        print("没有更新：" + summary(res))
        return 1
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
        r = subprocess.run(git_cmd(res["proxy"]) + ["-C", SKILL_DIR, "pull", "--ff-only", "--quiet"],
                           capture_output=True, timeout=180, env=git_env(res["proxy"]))
        if r.returncode != 0:
            print("更新失败：git pull 没成功：" + (r.stderr or b"").decode("utf-8", "replace").strip()[-300:])
            print(f"可以在浏览器打开 https://github.com/{REPO} 按 README 重新安装")
            return 1
        how = "git pull"
    else:
        tmp = tempfile.mkdtemp(prefix="rd-update-")
        try:
            new = os.path.join(tmp, "new")
            ok, how = fetch_release(f"v{latest}", new, res["proxy"])
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
    args, proxy = sys.argv[1:], None
    if "--proxy" in args:
        i = args.index("--proxy")
        if i + 1 >= len(args):
            print("--proxy 后面要跟代理地址（如 http://127.0.0.1:7890）或 none")
            return 2
        proxy = "" if args[i + 1].lower() == "none" else args[i + 1]
    if "--update" in args:
        return do_update(proxy)
    rc = pending_recheck()  # 开工时查不到、这次是手动复查：结果记为已复查，fetch_repo 不会再查一遍
    res = check(proxy=proxy, retry=proxy is None, recheck=rc)
    print(("repo-dissect 版本（复查）: " if rc else "repo-dissect 版本: ") + summary(res))
    for a in res["advice"]:
        print("  -", a)
    return {"newer": 10, "unknown": 20}.get(res["status"], 0)


if __name__ == "__main__":
    sys.exit(main())
