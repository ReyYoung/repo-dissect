"""repo-dissect 环境自检：列出可用的工具、网络和机器配置，并给出对应的降级做法。

用法: python3 check_env.py            （只用标准库，Python 3.8+，约 10 秒内结束）
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
    hub = registry_reachable("registry-1.docker.io") if registry_reachable else reach("https://registry-1.docker.io/v2/")
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
net_gh = reach("https://github.com")
net_api = reach("https://api.github.com")
add("网络 github.com", net_gh, "可访问" if net_gh else "不可访问", "访问不了 GitHub：请用户提供本地仓库路径或代码压缩包")
add("网络 api.github.com", net_api, "可访问" if net_api else "不可访问", "访问不了 GitHub API：社区数据标 ❓，注明未采集")
cpu, mem = os.cpu_count(), mem_gb()
free = shutil.disk_usage(os.getcwd()).free / 1024 ** 3
rows.append(("机器", "·", f"{cpu} 核 / {mem if mem else '?'} GB 内存 / 当前目录可用磁盘 {free:.0f} GB"))

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
print("运行项目: " + verdict)
