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


def run(cmd, timeout=8):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr).strip() else ""
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
if shutil.which("docker"):
    code, _ = run(["docker", "info"], timeout=6)
    add("docker", code == 0, "可用" if code == 0 else "已安装，守护进程不可用", "docker 不可用：跳过运行与截图（第 3 节），只做静态分析")
else:
    add("docker", False, "未安装", "没有 docker：跳过运行与截图（第 3 节），只做静态分析")
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
print("提示: 运行项目前还要对照它文档里的最低配置（CPU、内存、磁盘），不满足就跳过运行。")
