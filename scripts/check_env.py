"""repo-dissect 环境自检：列出可用的工具、网络和机器配置，并给出对应的降级做法。

用法: python3 check_env.py            （只用标准库，Python 3.8+，通常 10 秒内结束；GitHub 不通时会多花几秒找本机代理）
"""
import os
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request


for _s in (sys.stdout, sys.stderr):  # Windows 中文控制台（GBK）打印 ✓ ✗ 会崩
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def run(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        text = (r.stdout or r.stderr).decode("utf-8", "replace").strip()
        return r.returncode, text.splitlines()[0] if text else ""
    except Exception as e:  # 命令不存在、超时等
        return -1, type(e).__name__


def reach(url):
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=4)
        return True
    except urllib.error.HTTPError:
        return True  # 能收到 HTTP 响应就说明网络通
    except Exception:
        return False


def mem_gb():
    try:
        if sys.platform.startswith("linux"):
            for line in open("/proc/meminfo"):
                if line.startswith("MemTotal"):
                    return round(int(line.split()[1]) / 1024 / 1024, 1)
        if sys.platform == "darwin":
            return round(int(run(["sysctl", "-n", "hw.memsize"])[1]) / 1024 ** 3, 1)
    except Exception:
        pass
    return None


rows, tips = [], []


def add(name, ok, detail, tip=None):
    rows.append((name, "✓" if ok else "✗", detail))
    if not ok and tip:
        tips.append(tip)


add("python", sys.version_info >= (3, 8), platform.python_version(), "Python 低于 3.8：脚本无法运行，换用 python3.8+")
code, out = run(["git", "--version"])
add("git", code == 0, out or "未安装", "没有 git：无法克隆和核验链接，改为只读网页原文（结论标注“未经本地代码验证”）")
if shutil.which("gh"):
    code, out = run(["gh", "auth", "status"])
    add("gh", True, "已登录" if code == 0 else "已安装，未登录（公开仓库的 REST 接口仍可用）")
else:
    add("gh", False, "未安装", "没有 gh：社区数据改读 https://api.github.com/repos/<owner>/<repo>")
add("rg", bool(shutil.which("rg")), "可用" if shutil.which("rg") else "未安装", "没有 rg：用 grep -rn 代替")
loc = shutil.which("tokei") or shutil.which("cloc")
add("tokei/cloc", bool(loc), os.path.basename(loc) if loc else "未安装", "没有 tokei/cloc：用 git ls-files 按扩展名统计规模")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
try:
    from run_project import daemon_starter, registry_reachable, daemon_state, daemon_has_mirror, docker_info
except Exception:  # 只装了本脚本时
    daemon_starter = registry_reachable = daemon_state = daemon_has_mirror = docker_info = None
docker = "none"  # none / up / startable / stuck
if shutil.which("docker"):
    st = daemon_state() if daemon_state else ("up" if run(["docker", "info"], timeout=10)[0] == 0 else "down")
    if st == "up":
        docker = "up"
        add("docker", True, "可用")
    elif st == "denied":
        docker = "stuck"
        add("docker", False, "已安装，当前用户没有权限访问", "没有 Docker 权限：把用户加入 docker 组，或运行与截图交给用户电脑上的 Agent")
    else:
        name, cmd = daemon_starter() if daemon_starter else ("", None)
        docker = "startable" if cmd else "stuck"
        add("docker", bool(cmd), f"已安装，未运行；运行项目时可自动启动（{name}）" if cmd else
            f"已安装，守护进程未运行" + (f"，且无法自动启动：{name}" if name else ""),
            "Docker 无法自动启动：运行与截图交给用户电脑上的 Agent，或只做静态分析")
else:
    add("docker", False, "未安装", "没有 docker：运行与截图交给用户电脑上的 Agent，或只做静态分析")
hub = None
if docker != "none":
    # Docker 在运行时让它自己去连（它可能走系统代理），否则从本进程直连
    hub = (registry_reachable("registry-1.docker.io", "library/hello-world:latest" if docker == "up" else None)
           if registry_reachable else reach("https://registry-1.docker.io/v2/"))
    if not hub and docker == "up" and daemon_has_mirror and daemon_has_mirror(docker_info()):
        hub = True
        add("镜像仓库 Docker Hub", True, "直连不通，但 Docker 配了镜像加速或代理，以实际拉取为准")
    else:
        add("镜像仓库 Docker Hub", hub, "可访问" if hub else "不可访问",
            "访问不了 Docker Hub：只有镜像已在本地时才能运行项目，否则交给用户电脑上的 Agent")
try:
    import playwright  # noqa: F401
    pw = "Python 包可用"
except ImportError:
    pw = "npx 可用（需能下载浏览器）" if shutil.which("npx") else ""
add("playwright", bool(pw), pw or "不可用", "没有 Playwright：跳过截图和报告页的浏览器自查，只做脚本检查")
# ---- GitHub 连接：建连耗时、证书、失效代理、本机代理
try:
    import fetch_repo as fr
except Exception:
    fr = None
fetch_cmd = "python3 <技能目录>/scripts/fetch_repo.py <owner/repo> <ref> \"$OUT/src\""
gh_state = "ok"  # ok / slow / cert / down
local_px = None
dead_cfg = []  # 失效的代理设置：git 配置 / 环境变量
if fr:
    gp = fr.git_proxy_config() if shutil.which("git") else None
    if gp and not fr.proxy_alive(gp[1]):
        dead_cfg.append("git 配置里的代理")
        rows.append(("git 代理设置", "✗", f"{gp[0]}={gp[1]} 连不上"))
        tips.append(f"git 配置里的代理 {gp[1]} 连不上，git clone 会失败。本次可只对单条命令绕开：git -c http.proxy= clone …"
                    "（fetch_repo.py 会自动这样做）；要不要改全局配置由用户决定，不要擅自修改")
    ep = fr.env_proxy()
    if ep and not fr.proxy_alive(ep):
        dead_cfg.append("环境变量里的代理")
        rows.append(("环境变量代理", "✗", f"{ep} 连不上"))
        tips.append(f"环境变量里的代理 {ep} 连不上：本次命令可用 env -u HTTPS_PROXY -u HTTP_PROXY … 临时去掉，或先打开代理软件")
        ep = None
    pr = fr.tls_probe("github.com", ep if ep and fr.parse_proxy(ep) else None)
    if pr["ok"]:
        gh_state = "slow" if pr["secs"] > fr.SLOW else "ok"
        add("网络 github.com", True, f"可访问，建连 {pr['secs']:.1f} 秒" + ("（慢）" if gh_state == "slow" else "")
            + ("，经环境变量代理" if ep else ""))
        if gh_state == "slow":
            tips.append(f"连 GitHub 慢但可用（每次建连 {pr['secs']:.0f} 秒）：git clone 可能卡住，取码改用 {fetch_cmd}"
                        "（单连接整包下载，失败再逐文件下载并校验）")
    elif pr["cert"] is False:
        gh_state = "cert"
        add("网络 github.com", False, f"证书不受信（{pr['error']}）",
            "GitHub 证书不受信：通常是代理或安全软件在中间替换了证书。请用户把它的根证书导入系统，或关掉该软件的 HTTPS 扫描；"
            "Windows 上 git 也可试 -c http.sslBackend=openssl。不要关闭证书校验（sslVerify=false）。"
            "处理好之前请用户提供本地仓库路径或源码 ZIP（fetch_repo.py --from-archive）")
    else:
        gh_state = "down"
        add("网络 github.com", False, f"不可访问（{pr['error'][:60]}）")
    if gh_state in ("slow", "down"):
        lp = fr.local_proxies()
        if lp:
            url, secs = min(lp, key=lambda x: x[1])
            local_px = url
            rows.append(("本机代理", "·", f"{url} 可用，经它建连 {secs:.1f} 秒"))
            tips.append(f"发现本机代理 {url}：只对单条命令使用即可，例如 HTTPS_PROXY={url} git clone …，"
                        f"或 fetch_repo.py --proxy {url}（fetch_repo 默认会自动发现）；不需要改全局配置")
        elif gh_state == "down":
            tips.append("访问不了 GitHub：请用户打开代理后重试；或设置自己信任的镜像 RD_GITHUB_MIRROR；"
                        "或看项目在 Gitee / GitCode 有没有官方镜像；或提供本地仓库路径 / 源码 ZIP（fetch_repo.py --from-archive）")
    net_gh = gh_state in ("ok", "slow")
else:
    net_gh = reach("https://github.com")
    add("网络 github.com", net_gh, "可访问" if net_gh else "不可访问", "访问不了 GitHub：请用户提供本地仓库路径或代码压缩包")
net_api = reach("https://api.github.com")
add("网络 api.github.com", net_api, "可访问" if net_api else "不可访问", "访问不了 GitHub API：社区数据标 ❓，注明未采集")
cpu, mem = os.cpu_count(), mem_gb()
free = shutil.disk_usage(os.getcwd()).free / 1024 ** 3
rows.append(("机器", "·", f"{cpu} 核 / {mem if mem else '?'} GB 内存 / 当前目录可用磁盘 {free:.0f} GB"))


def probe_files():
    """探测 Agent 文件沙箱的两类限制：对已存在目录 mkdir 报错；.env 类文件读写被拦"""
    import tempfile
    from pathlib import Path
    res = {"mkdir": None, "env": None}
    try:  # 只在系统临时目录里试，不在用户的项目文件夹里留东西
        d = Path(tempfile.mkdtemp(prefix="rd-probe-"))
    except OSError as e:
        return {"mkdir": f"建不了临时目录：{e}", "env": None}
    try:
        try:
            d.mkdir(exist_ok=True)
        except OSError as e:
            res["mkdir"] = f"{type(e).__name__}: {e}"
        try:
            (d / ".env.example").write_text("RD_PROBE=1\n", encoding="utf-8")
            shutil.copy(str(d / ".env.example"), str(d / ".env"))
            (d / ".env").read_text(encoding="utf-8")
        except OSError as e:
            res["env"] = f"{type(e).__name__}: {e}"
    finally:
        shutil.rmtree(str(d), ignore_errors=True)
    return res


fp = probe_files()

# ---- 技能自身的版本：只检查和提醒，不自动更新
# 用上面探测 github.com 时走通的那条路线查：本机代理 > 有效的环境变量代理 > 代理设置失效时强制直连 > 系统默认。
# 自检已经选过路线，不再换路线重试；确认连不上 GitHub 时直接记为查不到，不再联网等超时
if local_px:
    vc_proxy = local_px
elif fr and ep and fr.parse_proxy(ep):
    vc_proxy = ep
elif dead_cfg and gh_state in ("ok", "slow"):
    vc_proxy = ""
else:
    vc_proxy = None
vc_offline = None
if gh_state in ("down", "cert") and not local_px:
    vc_offline = "github.com " + ("证书不受信" if gh_state == "cert" else "不通")
try:
    import version_check as vc
    ver = vc.check(proxy=vc_proxy, retry=False, offline=vc_offline)
except Exception as e:  # 检查脚本自己出错也要说出来，不能当作"已是最新"
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION"), encoding="utf-8") as f:
            _loc = f.read().strip()
    except OSError:
        _loc = None
    vc, ver = None, {"status": "unknown", "local": _loc, "latest": None, "newer": None, "advice": [],
                     "error": f"检查脚本出错 {type(e).__name__}: {e}"[:100], "proxy": None}
rows.insert(0, ("repo-dissect 版本", {"newer": "✗", "unknown": "✗", "latest": "✓"}.get(ver["status"], "·"),
                vc.summary(ver) if vc else f"{ver['local'] or '未知'}；最新版本查不到（{ver['error']}）"))
if ver["status"] != "unknown":  # 查不到时的说明在最后的"技能版本"一行里
    tips[:0] = ver["advice"]
add("文件沙箱", not (fp["mkdir"] or fp["env"]),
    "无限制" if not (fp["mkdir"] or fp["env"]) else "；".join(x for x in (
        "对已存在目录 mkdir 会报错（脚本已兼容）" if fp["mkdir"] else "",
        ".env 类文件读写被拦" if fp["env"] else "") if x),
    "文件沙箱拦截 .env 类文件：运行项目前先在前台执行 run_project.py prepare（触发授权），再把 run 放到后台；"
    "仍不行就交给用户电脑上的 Agent" if fp["env"] else None)

def dw(s):  # 显示宽度：中文算 2
    return sum(2 if ord(c) > 0x2E80 else 1 for c in s)


w = max(dw(r[0]) for r in rows) + 2
print("repo-dissect 环境自检")
for name, ok, detail in rows:
    print(f"  {ok} {name}{' ' * (w - dw(name))}{detail}")
if tips:
    print("降级做法:")
    for t in tips:
        print("  -", t)
if docker in ("up", "startable") and hub:
    verdict = "本机可以运行项目；具体项目还要看内存、磁盘和端口，届时用 run_project.py plan 生成运行决策卡片给用户选"
elif docker in ("up", "startable"):
    verdict = "Docker 可用但下载不了镜像：只有镜像已在本地的项目能运行；其余建议交给用户电脑上的 Agent（run_project.py handoff）"
else:
    verdict = "当前环境跑不了项目，静态分析不受影响；需要运行截图时交给用户电脑上的 Agent（run_project.py handoff）"
if fp["env"] and docker in ("up", "startable") and hub:
    verdict += "；注意本环境拦截 .env 类文件，运行前先在前台执行 run_project.py prepare"
print("运行项目: " + verdict)
cur = ver["local"] or "1.3.0 或更早"
if ver["status"] == "newer":
    print(f"技能版本: 当前 {cur}，GitHub 上已有 {ver['latest']}。在开工那次提问里问用户要不要先更新"
          f"（附上主要改动）；用户同意就执行 {vc.update_cmd(ver['proxy'])}，成功后重新读取 SKILL.md、重跑本脚本再开工；"
          "用户不同意、没回复或无人值守时，继续用当前版本。无论哪种，都在 index.md 记下版本和是否更新过")
elif ver["status"] == "unknown":
    print(f"技能版本: 当前 {cur}，GitHub 上的最新版本查不到（{ver['error']}），状态未知，不能当作已是最新。"
          "在开工那次提问里告诉用户：本地版本、最新版本未知、本次先用当前版本继续。取码成功后复查一次"
          "（fetch_repo.py 会自动复查并打印\"技能版本复查\"一行；用 git clone 取码、或取码后没看到这一行的，手动执行 "
          + (vc.check_cmd() if vc else "scripts/version_check.py") + "）；在 index.md 记下检查失败和复查结果")
elif ver["status"] == "latest":
    print(f"技能版本: {cur}，已是最新；在开工那次提问里带一句即可")
else:
    print(f"技能版本: {cur}，已按 RD_NO_UPDATE_CHECK 跳过检查；在开工那次提问里带一句即可")
if local_px:
    print(f"取代码: 直连{'慢' if gh_state == 'slow' else '不通'}，经本机代理 {local_px} 可用；用 fetch_repo.py 取码（会自动只对本次命令使用该代理）")
elif dead_cfg and gh_state in ("ok", "slow"):
    print(f"取代码: GitHub 能连上，但{'和'.join(dead_cfg)}失效，直接 git clone 会失败；用 fetch_repo.py 取码（会自动只对本次命令绕开）")
else:
    print("取代码: " + {"ok": "git clone 直接可用（也可用 fetch_repo.py，会自动选最快的方式）",
                       "slow": "GitHub 慢但可用，用 fetch_repo.py 取码（整包或逐文件，带校验）",
                       "cert": "证书不受信，先按上面的提示处理；不要关闭证书校验",
                       "down": "GitHub 不通：开代理、配置 RD_GITHUB_MIRROR，或请用户提供本地路径 / 源码 ZIP"}[gh_state])
