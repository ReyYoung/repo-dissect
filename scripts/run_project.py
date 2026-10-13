"""repo-dissect：把被拆项目在本机跑起来、截图、再清理干净（只用标准库，Python 3.8+；截图需要 Python playwright）。

用法（<OUT> 是本次拆解的输出目录，里面有 _vars.sh；代码默认在 <OUT>/src）:
  python3 run_project.py plan       <OUT> [--src 代码目录] [--compose 文件] [--min-cpu 4] [--min-mem 16] [--min-disk 50]
  python3 run_project.py run        <OUT> [--timeout-min 25] [--keep] [--pages pages.json] [--login 账号:密码] [--base 地址]
  python3 run_project.py screenshot <OUT> [--pages pages.json] [--login 账号:密码] [--base http://localhost]
  python3 run_project.py cleanup    <OUT>
  python3 run_project.py handoff    <OUT>
  --pages 不写时使用 $OUT/run/pages.json；格式 [{"name": "01-知识库列表", "path": "/knowledge", "wait_ms": 1500}]
  --login 也可用环境变量 RD_LOGIN 传入（避免密码出现在进程列表里）

plan       只检查，不动项目和 Docker：Docker 是否可用/可自动启动、镜像仓库能否访问、内存磁盘、端口、同名容器、
           ARM 兼容、项目要求的主机权限；在 $OUT/run/work 准备一份项目副本，生成"运行决策卡片"（$OUT/run/plan.md）。
           退出码 0=可以运行，2=需先处理，3=本环境跑不了
run        用户选定"在本机运行"后执行：启动 Docker → 拉镜像 → 启动 → 等就绪 → 截图 → 自动清理（--keep 则保留运行）
screenshot 对运行中的项目按 pages.json 逐页截图，同时保存页面文字（看不了图片的 Agent 以文字为准）
cleanup    停止并删除本次启动的容器、网络和本次新建的数据卷，删除项目副本（只动项目名 rd-<仓库名>-<编号> 下的资源）
handoff    本环境跑不了时，生成交给用户电脑上 Agent 的一句话接力指令（$OUT/run-locally.md）
"""
import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

COMPOSE_NAMES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")
OVERRIDE_NAMES = ("docker-compose.override.yml", "docker-compose.override.yaml", "compose.override.yml", "compose.override.yaml")
WEB_TARGETS = (80, 443, 3000, 8080, 8000, 5000, 5173, 8501, 7860, 9000)
SKIP_COPY = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".next"}
BUILD_MIN = 10   # 每个需现场构建的服务估 10 分钟
START_MIN = 5    # 启动估 5 分钟
MB_PER_S = 10    # 下载速度估 10 MB/s


# ---------------------------------------------------------------- 基础工具
def utf8_stdio():
    """Windows 中文控制台（GBK）打印 emoji 会崩，统一用 UTF-8 输出"""
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def sh(cmd, timeout=60, cwd=None):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=cwd)
        return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: 未安装"
    except subprocess.TimeoutExpired:
        return 124, "", f"超时（{timeout} 秒）"


def load_vars(out):
    v = {}
    p = out / "_vars.sh"
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*(\w+)=['\"]?(.*?)['\"]?\s*$", line)
            if m:
                v[m.group(1)] = m.group(2)
    return v


class Log:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, msg, echo=True):
        line = f"[{datetime.datetime.now():%H:%M:%S}] {msg}"
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if echo:
            print(line, flush=True)


def gb(n):
    return round(n / 1024 ** 3, 1)


def jloads(text, default=None):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return default


def is_local_url(url):
    return bool(re.match(r"https?://(localhost|127\.0\.0\.1|\[::1\])(:|/|$)", url))


def http(url, headers=None, timeout=6, method=None):
    """本机地址不走代理（用户开着代理软件时，localhost 走代理会一直打不开）"""
    req = urllib.request.Request(url, headers=headers or {}, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if is_local_url(url) \
        else urllib.request.build_opener()
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:  # 网络不通、DNS 失败、超时
        return 0, {}, str(e).encode()


def in_sandbox():
    """粗略判断是否在云端 / 沙箱 / 容器里（这类环境通常跑不了大型多容器项目，宜交给用户电脑）"""
    env = os.environ
    if any(k in env for k in ("IS_SANDBOX", "CODEX_SANDBOX", "CODEX_SANDBOX_NETWORK_DISABLED", "KUBERNETES_SERVICE_HOST",
                              "CODESPACES", "GITPOD_WORKSPACE_ID")):
        return True
    if env.get("CLAUDE_CODE_REMOTE") == "true":
        return True
    return platform.system() == "Linux" and Path("/.dockerenv").exists()


# ---------------------------------------------------------------- Docker 状态
def docker_cli():
    return shutil.which("docker") is not None


def daemon_state():
    """up / down / denied（没权限）/ none（没装）"""
    code, _, err = sh(["docker", "info", "--format", "{{json .}}"], timeout=20)
    if code == 0:
        return "up"
    if code == 127:
        return "none"
    if re.search(r"permission denied", err, re.I):
        return "denied"
    return "down"


def daemon_up():
    return daemon_state() == "up"


def daemon_starter():
    """返回 (说明, 启动命令)；无法自动启动返回 (原因, None)"""
    sysname = platform.system()
    if sysname == "Darwin":
        ctx = sh(["docker", "context", "show"], timeout=10)[1].strip() if docker_cli() else ""
        apps = []
        if Path("/Applications/OrbStack.app").exists() or shutil.which("orb"):
            apps.append(("orbstack", "OrbStack", ["open", "-a", "OrbStack"]))
        if Path("/Applications/Docker.app").exists():
            apps.append(("desktop", "Docker Desktop", ["open", "-a", "Docker"]))
        if shutil.which("colima"):
            apps.append(("colima", "Colima", ["colima", "start"]))
        for key, name, cmd in apps:  # 优先当前 docker context 对应的那个
            if key in ctx:
                return name, cmd
        if apps:
            return apps[0][1], apps[0][2]
        return "没有找到 OrbStack / Docker Desktop / Colima", None
    if sysname == "Linux":
        root = hasattr(os, "geteuid") and os.geteuid() == 0
        can_sudo = root or sh(["sudo", "-n", "true"], timeout=5)[0] == 0
        if shutil.which("systemctl") and Path("/run/systemd/system").exists():
            if not can_sudo:
                return "启动 Docker 服务需要管理员权限", None
            return "Docker 服务", (["systemctl", "start", "docker"] if root else ["sudo", "-n", "systemctl", "start", "docker"])
        if shutil.which("dockerd"):
            if not can_sudo:
                return "启动 dockerd 需要管理员权限", None
            pre = [] if root else ["sudo", "-n"]
            return "dockerd", pre + ["sh", "-c", "nohup dockerd >/tmp/repo-dissect-dockerd.log 2>&1 &"]
        return "没有找到 dockerd", None
    if sysname == "Windows":
        p = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Docker" / "Docker" / "Docker Desktop.exe"
        if p.exists():
            return "Docker Desktop", [str(p)]
        return "没有找到 Docker Desktop", None
    return f"不支持的系统 {sysname}", None


def start_daemon(log, wait=180):
    st = daemon_state()
    if st == "up":
        return True
    if st == "denied":
        log("当前用户没有权限访问 Docker")
        return False
    name, cmd = daemon_starter()
    if not cmd:
        log(f"Docker 未运行，且无法自动启动：{name}")
        return False
    log(f"Docker 未运行，正在启动 {name} …")
    try:  # 不等命令结束（colima 首次启动可能要几分钟），只等 Docker 就绪
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                         **({"start_new_session": True} if os.name != "nt" else {}))
    except Exception as e:
        log(f"启动命令执行失败：{e}")
        return False
    t0 = time.time()
    while time.time() - t0 < wait:
        if daemon_up():
            log(f"Docker 已就绪（用时 {int(time.time() - t0)} 秒）")
            return True
        time.sleep(3)
    log(f"等待 {wait} 秒后 Docker 仍未就绪")
    return False


def docker_info():
    code, out, _ = sh(["docker", "info", "--format", "{{json .}}"], timeout=20)
    return jloads(out, {}) if code == 0 else {}


def docker_vm(info):
    """Docker 是否跑在虚拟机里（Mac / Windows / Docker Desktop），决定内核参数改在哪"""
    os_name = (info.get("OperatingSystem") or "").lower()
    return platform.system() != "Linux" or "docker desktop" in os_name or "orbstack" in os_name


def registry_reachable(host):
    code, _, _ = http(f"https://{host}/v2/", timeout=6)
    return code in (200, 401, 403)


def daemon_has_mirror(info):
    """Docker 配了镜像加速或与当前环境不同的代理时，本脚本直连仓库失败不代表 Docker 拉不下来"""
    mirrors = (info.get("RegistryConfig") or {}).get("Mirrors") or []
    dp = info.get("HTTPSProxy") or info.get("HTTPProxy") or ""
    ep = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
    return bool(mirrors) or bool(dp and dp != ep)


# ---------------------------------------------------------------- 代码副本与 compose
def find_compose(src, given=None):
    """返回 (选中的 compose 文件, 其他候选)"""
    if given:
        p = Path(given) if Path(given).is_absolute() else src / given
        return (p if p.is_file() else None), []
    cands = []
    for d in [src] + [x for x in sorted(src.iterdir()) if x.is_dir() and not x.name.startswith(".")]:
        for n in COMPOSE_NAMES:
            if (d / n).is_file():
                cands.append(d / n)
    for d in sorted(src.glob("*/*")):
        if d.is_dir() and d.name in ("docker", "deploy", "compose"):
            for n in COMPOSE_NAMES:
                if (d / n).is_file():
                    cands.append(d / n)
    if not cands:
        return None, []
    pick = cands[0]
    others = sorted({p for p in pick.parent.glob("*compose*.y*ml")
                     if p != pick and p.name not in OVERRIDE_NAMES} | set(cands[1:]))
    return pick, others


def prepare_work(src, work, log=None, fresh=False):
    """把项目复制到 $OUT/run/work：容器写入的数据、生成的 .env 都落在副本里，不碰原项目。plan 每次重新复制"""
    if (work / ".rd-copy-done").is_file() and not fresh:
        return
    if work.exists():
        shutil.rmtree(str(work), ignore_errors=True)
    shutil.copytree(str(src), str(work), symlinks=True, dirs_exist_ok=True,
                    ignore=lambda d, names: [n for n in names if n in SKIP_COPY])
    (work / ".rd-copy-done").write_text("1", encoding="utf-8")
    if log:
        log(f"已准备项目副本：{work}")


def prepare_env(compose_dir):
    """compose 目录没有 .env 而有 .env.example 等模板时，在副本里用模板生成 .env"""
    if (compose_dir / ".env").exists():
        return None
    for n in (".env.example", ".env.sample", "env.example", ".env.template", ".env.dist"):
        if (compose_dir / n).is_file():
            shutil.copy(str(compose_dir / n), str(compose_dir / ".env"))
            return n
    return None


def compose_files(plan, out):
    files = ["-f", plan["compose_work"]]
    for n in OVERRIDE_NAMES:  # 用 -f 时 compose 不会自动加载项目自带的 override，要显式带上
        p = Path(plan["compose_work"]).parent / n
        if p.is_file():
            files += ["-f", str(p)]
            break
    ov = out / "run" / "compose.override.yml"
    if ov.is_file():
        files += ["-f", str(ov)]
    return files


def compose_cmd(plan, out, extra):
    return (["docker", "compose", "-p", plan["project"], "--project-directory", str(Path(plan["compose_work"]).parent)]
            + compose_files(plan, out) + extra)


def compose_config(plan, out):
    """返回 (配置, 解析方式, 错误)。优先 docker compose config（处理 include、.env、profiles），不可用时正则粗解析"""
    err = ""
    if docker_cli():
        code, o, e = sh(compose_cmd(plan, out, ["config", "--format", "json"]), timeout=90)
        cfg = jloads(o) if code == 0 else None
        if isinstance(cfg, dict):
            return cfg, "docker compose config", ""
        err = (e or o).strip()
    compose = Path(plan["compose_work"])
    text = compose.read_text(encoding="utf-8", errors="replace")
    services, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^  ([A-Za-z0-9_.-]+):\s*$", line)
        if m:
            cur = m.group(1)
            services[cur] = {"ports": []}
            continue
        if cur:
            m = re.match(r"^\s+image:\s*['\"]?([^'\"\s#]+)", line)
            if m:
                services[cur]["image"] = m.group(1)
            m = re.match(r"^\s+-\s*['\"]?(?:[\d.]+:)?(\d+|\$\{[^}]+\}):(\d+)", line)
            if m:
                services[cur]["ports"].append({"published": m.group(1), "target": int(m.group(2))})
    return {"services": services}, "正则粗解析（结果仅供参考）", err


def compose_ok():
    return sh(["docker", "compose", "version"], timeout=20)[0] == 0


# ---------------------------------------------------------------- 镜像
def image_ref(image):
    """('registry-1.docker.io', 'library/redis', 'tag 或 digest')"""
    name, tag = image, "latest"
    if "@" in name:
        name, tag = name.split("@", 1)
        name = re.sub(r":[^/]+$", "", name)  # x:tag@sha256:… 以 digest 为准
    elif re.search(r":[^/]+$", name):
        name, tag = name.rsplit(":", 1)
    first = name.split("/")[0]
    if ("." in first or ":" in first or first == "localhost") and "/" in name:
        host, repo = first, name.split("/", 1)[1]
    else:
        host, repo = "registry-1.docker.io", (name if "/" in name else "library/" + name)
    return host, repo, tag


def image_info(image, arch):
    """匿名查询镜像清单：是否有本机架构版本、压缩后大小。Docker Hub 不查（查清单会消耗匿名拉取次数）"""
    host, repo, tag = image_ref(image)
    none = {"arch_ok": None, "size": None}
    if host == "registry-1.docker.io":
        return none
    acc = ", ".join(["application/vnd.oci.image.index.v1+json",
                     "application/vnd.docker.distribution.manifest.list.v2+json",
                     "application/vnd.oci.image.manifest.v1+json",
                     "application/vnd.docker.distribution.manifest.v2+json"])
    url = f"https://{host}/v2/{repo}/manifests/{tag}"
    code, hdr, body = http(url, {"Accept": acc})
    h = {"Accept": acc}
    if code == 401:
        auth = hdr.get("WWW-Authenticate") or hdr.get("Www-Authenticate") or ""
        p = dict(re.findall(r'(\w+)="([^"]*)"', auth))
        if p.get("realm"):
            c2, _, b2 = http(f"{p['realm']}?service={p.get('service', '')}&scope=repository:{repo}:pull")
            j = jloads(b2, {}) if c2 == 200 else {}
            token = (j.get("token") or j.get("access_token")) if isinstance(j, dict) else None
            if token:
                h["Authorization"] = f"Bearer {token}"
                code, hdr, body = http(url, h)
    m = jloads(body) if code == 200 else None
    if not isinstance(m, dict):
        return none
    if "manifests" in m:
        plats = [(d.get("platform") or {}).get("architecture") for d in m["manifests"]]
        pick = next((d for d in m["manifests"] if (d.get("platform") or {}).get("architecture") == arch), None)
        target = pick or next((d for d in m["manifests"] if (d.get("platform") or {}).get("architecture") == "amd64"), None)
        res = {"arch_ok": pick is not None, "size": None, "archs": plats}
        if target:
            c3, _, b3 = http(f"https://{host}/v2/{repo}/manifests/{target['digest']}", h)
            m3 = jloads(b3) if c3 == 200 else None
            if isinstance(m3, dict):
                res["size"] = sum(l.get("size", 0) for l in m3.get("layers", []))
        return res
    return {"arch_ok": None, "size": sum(l.get("size", 0) for l in m.get("layers", []))}


def local_image(image):
    return docker_cli() and sh(["docker", "image", "inspect", image], timeout=20)[0] == 0


# ---------------------------------------------------------------- 主机
def port_busy(port):
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", int(port))) == 0
    finally:
        s.close()


def port_owner(port):
    """占用端口的程序名（有 lsof 时），查不到返回空串"""
    if not shutil.which("lsof"):
        return ""
    _, o, _ = sh(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], timeout=10)
    rows = [ln.split() for ln in o.splitlines()[1:] if ln.strip()]
    return rows[0][0] if rows else ""


def doc_requirements(src):
    """从 README / 文档里找"CPU >= 4 cores、RAM >= 16 GB、Disk >= 50 GB"之类的最低配置（尽力而为）"""
    req = {}
    files = list(src.glob("README*.md")) + list(src.glob("docs/**/*quick*start*.md*"))[:5]
    text = "\n".join(f.read_text(encoding="utf-8", errors="replace")[:200000] for f in files[:8])
    for key, pat in (("cpu", r"CPU\s*(?:>=|≥|>)\s*(\d+)"), ("mem", r"(?:RAM|Memory|内存)\s*(?:>=|≥|>)\s*(\d+)\s*G"),
                     ("disk", r"(?:Disk|磁盘)\s*(?:>=|≥|>)\s*(\d+)\s*G")):
        m = re.search(pat, text, re.I)
        if m:
            req[key] = int(m.group(1))
    return req


def host_arch(info):
    a = (info.get("Architecture") or platform.machine()).lower()
    return {"x86_64": "amd64", "aarch64": "arm64"}.get(a, a)


def host_mem():
    try:
        if sys.platform.startswith("linux"):
            for line in open("/proc/meminfo"):
                if line.startswith("MemTotal"):
                    return round(int(line.split()[1]) / 1024 / 1024, 1)
        if sys.platform == "darwin":
            return gb(int(sh(["sysctl", "-n", "hw.memsize"])[1].strip()))
    except Exception:
        pass
    return None


def max_map_count_host():
    try:
        return int(Path("/proc/sys/vm/max_map_count").read_text().strip())
    except Exception:
        return None


# ---------------------------------------------------------------- compose 内容分析
def port_list(s):
    res = []
    for p in s.get("ports") or []:
        if isinstance(p, dict):
            pub, tgt = p.get("published"), p.get("target")
        else:  # 正则解析或短写法字符串
            m = re.match(r"(?:[\d.]+:)?(\d+):(\d+)", str(p))
            pub, tgt = (m.group(1), m.group(2)) if m else ("", p)
        pub = str(pub) if pub not in (None, "") else ""
        try:
            tgt = int(str(tgt).split("/")[0])
        except ValueError:
            tgt = 0
        res.append({"published": pub if pub.isdigit() else "", "target": tgt})
    return res


HARMLESS_RO = {"/etc/localtime", "/etc/timezone", "/usr/share/zoneinfo"}
SENSITIVE_CAPS = {"ALL", "SYS_ADMIN", "NET_ADMIN", "SYS_PTRACE", "SYS_MODULE", "SYS_RAWIO", "DAC_READ_SEARCH"}


def host_access(name, s, work):
    """项目要求的主机权限：特权、挂载 docker.sock 或本机目录、共享主机网络/进程、高危 capability、设备"""
    risks = []
    if s.get("privileged"):
        risks.append(f"{name}：特权模式（privileged）")
    if s.get("network_mode") == "host":
        risks.append(f"{name}：使用主机网络（network_mode: host）")
    if s.get("pid") == "host":
        risks.append(f"{name}：可见主机进程（pid: host）")
    caps = {str(c).upper().replace("CAP_", "") for c in (s.get("cap_add") or [])} & SENSITIVE_CAPS
    if caps:
        risks.append(f"{name}：高危权限 {', '.join(sorted(caps))}")
    if s.get("devices"):
        risks.append(f"{name}：访问主机设备")
    work_s = str(work.resolve())
    for v in s.get("volumes") or []:
        if isinstance(v, dict):
            typ, srcp = v.get("type"), v.get("source") or ""
        else:
            parts = str(v).split(":")
            srcp = parts[0] if len(parts) > 1 else ""
            typ = "bind" if srcp.startswith(("/", ".", "~")) else "volume"
        if typ != "bind" or not srcp:
            continue
        if "docker.sock" in srcp:
            risks.append(f"{name}：挂载 Docker 控制接口（{srcp}），等于能控制本机所有容器")
            continue
        try:
            rp = str(Path(os.path.expanduser(srcp)).resolve())
        except Exception:
            rp = srcp
        ro = (v.get("read_only") if isinstance(v, dict) else str(v).endswith(":ro"))
        if ro and (srcp in HARMLESS_RO or rp in HARMLESS_RO or rp.startswith("/usr/share/zoneinfo/")):
            continue
        if not (rp == work_s or rp.startswith(work_s + os.sep)):
            risks.append(f"{name}：挂载项目以外的本机目录 {srcp}" + ("（只读）" if ro else ""))
    return risks


# ---------------------------------------------------------------- plan
def project_name(v, out):
    base = re.sub(r"[^a-z0-9]+", "-", (v.get("REPO", "") or out.name).split("/")[-1].lower()).strip("-")
    if not base or base == "local":
        base = re.sub(r"[^a-z0-9]+", "-", out.name.lower()).strip("-") or "app"
    return f"rd-{base[:30]}-{hashlib.sha1(str(out).encode()).hexdigest()[:6]}"


def cmd_plan(out, args):
    v = load_vars(out)
    rundir = out / "run"
    rundir.mkdir(exist_ok=True)
    old = jloads((rundir / "plan.json").read_text(encoding="utf-8"), {}) if (rundir / "plan.json").is_file() else {}
    src = Path(args.get("src") or old.get("src") or (out / "src")).expanduser().resolve()
    if not src.is_dir():
        sys.exit(f"找不到代码目录 {src}：GitHub 项目在 <OUT>/src；本地仓库用 --src <路径> 指定")
    stale = rundir / "compose.override.yml"
    if stale.exists():
        stale.unlink()
    blockers, fixes, notes, changes, risks = [], [], [], [], []
    plan = {"created": datetime.datetime.now().isoformat(timespec="seconds"), "out": str(out), "src": str(src),
            "repo": v.get("REPO", ""), "sha": v.get("SHA", ""), "project": project_name(v, out),
            "sandbox": in_sandbox()}

    def block(msg, kind="local"):
        blockers.append({"msg": msg, "kind": kind})

    compose, others = find_compose(src, args.get("compose"))
    if not compose:
        block("仓库里没有 docker-compose 文件，脚本不知道怎么启动这个项目（可按项目文档在容器里手动启动，或只做静态分析）", "project")
        return finish_plan(out, plan, blockers, fixes, notes, changes, risks)
    try:
        rel = compose.resolve().relative_to(src)
    except ValueError:
        sys.exit(f"compose 文件 {compose} 不在代码目录 {src} 里")
    plan["compose"] = str(rel)
    if others:
        def show(o):
            try:
                return str(o.resolve().relative_to(src))
            except ValueError:
                return str(o)
        mac = [o for o in others if re.search(r"mac|arm", o.name, re.I)]
        tip = f"；在这台 Mac 上可能应该用 {show(mac[0])}（用 --compose 指定后重新检查）" if mac and platform.system() == "Darwin" else ""
        notes.append(f"使用 {rel}；另有 {'、'.join(show(o) for o in others[:6])}{tip}")
    # 项目副本（已有本次项目的容器在运行时不重建副本，免得删掉运行中容器挂载的目录）
    work = rundir / "work"
    cw = work / rel
    running = False
    if old.get("project") and old.get("compose_work") and docker_cli() and (work / ".rd-copy-done").is_file():
        running = bool(sh(compose_cmd(dict(old, compose_work=str(cw)), out, ["ps", "-q"]), timeout=30)[1].strip())
    if running:
        fixes.append(f"上次用 --keep 启动的项目还在运行：先执行 run_project.py cleanup {out}，再重新检查")
    else:
        try:
            prepare_work(src, work, fresh=True)
        except (shutil.Error, OSError) as e:
            block(f"准备项目副本失败（{str(e)[:160]}）：可能是上次运行时容器写入的文件属于管理员，手动删除 {work} 后重新检查")
            return finish_plan(out, plan, blockers, fixes, notes, changes, risks)
    plan["work"] = str(work)
    plan["compose_work"] = str(cw)
    envtpl = prepare_env(cw.parent)
    if envtpl:
        changes.append(f"在项目副本里用 {envtpl} 生成 .env（项目默认配置）")
    # Docker
    st = daemon_state() if docker_cli() else "none"
    if st == "none":
        block("这台机器没有安装 Docker（Mac 推荐装 OrbStack 或 Docker Desktop）")
        dstate = "未安装"
    elif st == "up":
        dstate = "运行中"
    elif st == "denied":
        block("当前用户没有权限访问 Docker（需要加入 docker 组，或用有权限的账号运行）")
        dstate = "没有访问权限"
    else:
        name, cmd = daemon_starter()
        if cmd:
            dstate = f"未运行，可自动启动（{name}）"
            changes.append(f"启动 {name}")
        else:
            dstate = f"未运行，无法自动启动：{name}"
            block(f"Docker 未运行，且无法自动启动（{name}）")
    if st != "none" and not compose_ok():
        block("没有 Docker Compose v2（docker compose 命令不可用）")
    up = st == "up"
    info = docker_info() if up else {}
    arch = host_arch(info)
    plan["arch"] = arch
    plan["docker"] = dstate
    # 解析 compose
    cfg, how, err = compose_config(plan, out)
    services = cfg.get("services") or {}
    plan["parsed_by"] = how
    if err:
        first = [ln.strip() for ln in err.splitlines() if ln.strip()][:2]
        if re.search(r"env file .* not found|\.env.*no such file", err, re.I):
            fixes.append("项目缺少 .env 配置文件且没有模板可用：" + "；".join(first))
        elif re.search(r"required variable|is missing a value", err, re.I):
            fixes.append("项目要求先设置环境变量：" + "；".join(first))
        elif st != "none":
            fixes.append("compose 文件解析出错：" + "；".join(first))
    if not services:
        block("compose 文件里没有解析出任何服务", "project")
        return finish_plan(out, plan, blockers, fixes, notes, changes, risks)
    plan["services"] = {}
    for k, s in services.items():
        plan["services"][k] = {"image": s.get("image"), "build": bool(s.get("build")), "ports": port_list(s),
                               "container_name": s.get("container_name"), "base_images": base_images(s.get("build"), cw.parent)}
        risks += host_access(k, s, work)
    # 数据卷：已存在的同名卷会被直接使用，清理时不删
    for vk, vv in (cfg.get("volumes") or {}).items():
        vv = vv or {}
        vname = vv.get("name") or vk
        if vv.get("external"):
            notes.append(f"使用已有数据卷 {vname}（external），清理时不会删除")
        elif vv.get("name") and up:
            code, o, _ = sh(["docker", "volume", "inspect", "--format",
                             '{{index .Labels "com.docker.compose.project"}}', vname], timeout=15)
            if code == 0 and o.strip() != plan["project"]:
                notes.append(f"数据卷 {vname} 已存在且不是本次创建的，项目会直接使用它（可能读写里面的数据），清理时不会删除")
    # 同名容器
    if up:
        for k, s in plan["services"].items():
            cn = s.get("container_name")
            if not cn:
                continue
            _, o, _ = sh(["docker", "ps", "-a", "--filter", f"name=^/{cn}$", "--format",
                          '{{.Names}}\t{{.Label "com.docker.compose.project"}}'], timeout=15)
            rows = [ln.split("\t") for ln in o.splitlines() if ln.strip()]
            if rows and (len(rows[0]) < 2 or rows[0][1] != plan["project"]):
                fixes.append(f"已有同名容器 {cn}（不是本次启动的，可能是你之前部署的同一个项目）：先停止并删除它，或确认不再需要后告诉我")
    # 镜像
    mirror = daemon_has_mirror(info) if up else False
    cache = {i["image"]: i for i in old.get("images", []) if i.get("status") == "需下载"}
    imgs, hosts, seen, need_amd64, builds = [], {}, {}, [], []
    for k, s in plan["services"].items():
        img = s.get("image")
        if s["build"] and not (img and up and local_image(img)):
            builds.append(k)
            for b in s.get("base_images") or []:  # 构建要用的基础镜像也得能下载
                if up and local_image(b):
                    continue
                h = image_ref(b)[0]
                if h not in hosts:
                    hosts[h] = registry_reachable(h)
            continue
        if not img:
            continue
        if img in seen:
            imgs.append(dict(seen[img], service=k))
            if seen[img].get("arch_ok") is False:
                need_amd64.append(k)
            continue
        item = {"service": k, "image": img}
        if not up:
            item["status"] = "未知（Docker 未运行）"
        elif local_image(img):
            item["status"] = "本地已有"
        else:
            host = image_ref(img)[0]
            if host not in hosts:
                hosts[host] = registry_reachable(host)
            if not hosts[host] and not (mirror and host == "registry-1.docker.io"):
                item["status"] = "仓库不可访问"
            else:
                ii = cache.get(img) or image_info(img, arch)
                item.update({"status": "需下载", "size": ii.get("size"), "arch_ok": ii.get("arch_ok")})
                if ii.get("arch_ok") is False:
                    need_amd64.append(k)
        seen[img] = item
        imgs.append(item)
    plan["images"] = imgs
    plan["builds"] = builds
    if builds:
        notes.append(f"{len(builds)} 个服务需要现场构建镜像（{'、'.join(builds)}），耗时较长且需要能下载依赖")
    bad_hosts = sorted(h for h, ok in hosts.items() if not ok and not (mirror and h == "registry-1.docker.io"))
    if bad_hosts:
        block("访问不了镜像仓库：" + "、".join(bad_hosts) + "（网络受限的云端、沙箱或内网环境常见）", "network")
    elif not up and st == "down":
        for h in sorted({image_ref(i["image"])[0] for i in imgs}):
            if not registry_reachable(h):
                notes.append(f"访问不了镜像仓库 {h}；Docker 启动后才能确认镜像是否已在本地，不在本地则运行会失败")
    if need_amd64:
        if arch == "arm64":
            notes.append(f"{len(need_amd64)} 个服务只有 x86 镜像（{'、'.join(need_amd64)}），会按 x86 转译运行，速度较慢")
            changes.append("为只有 x86 镜像的服务指定 x86 平台（写在 run/ 下的覆盖文件里，不改项目文件）")
        else:
            block(f"{'、'.join(need_amd64)} 没有本机架构（{arch}）的镜像", "project")
    plan["need_amd64"] = need_amd64
    pull = {i["image"]: i for i in imgs if i.get("status") == "需下载"}
    known = sum(i["size"] for i in pull.values() if i.get("size"))
    plan["to_pull"] = len(pull)
    plan["size_unknown"] = sum(1 for i in pull.values() if not i.get("size"))
    plan["download_gb"] = gb(known) if known else None
    # 资源
    req = doc_requirements(src)
    for k in ("cpu", "mem", "disk"):
        if args.get("min_" + k):
            req[k] = float(args["min_" + k])
    cpu = info.get("NCPU") or os.cpu_count()
    mem = gb(info["MemTotal"]) if info.get("MemTotal") else host_mem()
    disk = gb(shutil.disk_usage(str(Path.home())).free)
    plan["resources"] = {"cpu": cpu, "mem_gb": mem, "disk_gb": disk, "required": req}
    if req.get("mem") and mem and mem < req["mem"]:
        hm = host_mem()
        if docker_vm(info) and hm and hm >= req["mem"]:
            fixes.append(f"Docker 可用内存 {mem} GB，低于项目要求 {req['mem']:g} GB；本机有 {hm} GB，"
                         f"在 OrbStack / Docker Desktop 设置里把内存上限调到 {int(req['mem'])} GB 以上即可")
        elif mem < req["mem"] * 0.75:
            block(f"内存 {mem} GB，项目要求至少 {req['mem']:g} GB")
        else:
            notes.append(f"内存 {mem} GB，略低于项目要求 {req['mem']:g} GB，可能能跑但会慢")
    if req.get("cpu") and cpu and cpu < req["cpu"]:
        notes.append(f"CPU {cpu} 核，低于项目要求 {int(req['cpu'])} 核，启动会慢")
    est_gb = (plan["download_gb"] or 0) + plan["size_unknown"] * 1.0
    need_disk = req.get("disk") or est_gb * 2.5
    if need_disk and disk < need_disk:
        block(f"可用磁盘 {disk} GB，预计需要 {round(need_disk)} GB")
    # 端口
    busy = []
    for k, s in plan["services"].items():
        for p in s["ports"]:
            if p["published"] and not running and port_busy(p["published"]):
                who = port_owner(p["published"])
                busy.append(f"{p['published']}（{k} 要用{'，现被 ' + who + ' 占用' if who else ''}）")
    if busy:
        fixes.append("端口被占用：" + "、".join(busy) + "。关掉占用这些端口的程序，或改项目 .env 里的端口后告诉我")
    plan["ports"] = sorted({p["published"] for s in plan["services"].values() for p in s["ports"] if p["published"]}, key=int)
    plan["url"], plan["web"] = web_url(plan["services"])
    # Elasticsearch / OpenSearch 需要的内核参数
    if any(re.search(r"elasticsearch|opensearch", (s.get("image") or "")) for s in plan["services"].values()):
        if docker_vm(info) or (not up and platform.system() != "Linux"):
            plan["sysctl"] = "vm"
            changes.append("把 Docker 虚拟机的内核参数 vm.max_map_count 调到至少 262144（Elasticsearch 的要求；只升不降，重启 Docker 后恢复）")
        else:
            cur = max_map_count_host()
            if cur is not None and cur < 262144:
                root = hasattr(os, "geteuid") and os.geteuid() == 0
                if root or sh(["sudo", "-n", "true"], timeout=5)[0] == 0:
                    plan["sysctl"] = "host"
                    changes.append(f"把本机内核参数 vm.max_map_count 从 {cur} 调到 262144（Elasticsearch 的要求；重启电脑后恢复）")
                else:
                    fixes.append(f"Elasticsearch 要求内核参数 vm.max_map_count ≥ 262144（现在是 {cur}）："
                                 "请执行 sudo sysctl -w vm.max_map_count=262144")
    return finish_plan(out, plan, blockers, fixes, notes, changes, risks)


def base_images(build, compose_dir):
    """构建所需的基础镜像（Dockerfile 里的 FROM，跳过多阶段构建的阶段名和带变量的写法）"""
    if not build:
        return []
    if isinstance(build, str):
        build = {"context": build}
    ctx = Path(build.get("context") or ".")
    ctx = ctx if ctx.is_absolute() else compose_dir / ctx
    df = Path(build.get("dockerfile") or "Dockerfile")
    df = df if df.is_absolute() else ctx / df
    try:
        text = df.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    stages, res = set(), []
    for m in re.finditer(r"(?im)^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", text):
        img, alias = m.group(1), m.group(2)
        if img.lower() not in stages and "$" not in img and img.lower() != "scratch":
            res.append(img)
        if alias:
            stages.add(alias.lower())
    return res


def web_url(services):
    """返回 (地址, [服务, 容器端口])；端口随机分配时地址为 None，运行后再解析"""
    best = None
    for name, s in services.items():
        for p in s.get("ports", []):
            tgt = p.get("target") or 0
            if tgt in WEB_TARGETS:
                rank = WEB_TARGETS.index(tgt) + (0 if p["published"] else 100)
                if best is None or rank < best[0]:
                    best = (rank, name, tgt, p["published"])
    if not best:
        return None, None
    _, name, tgt, pub = best
    if not pub:
        return None, [name, tgt]
    scheme = "https" if tgt == 443 else "http"
    port = "" if (scheme == "http" and pub == "80") or (scheme == "https" and pub == "443") else ":" + pub
    return f"{scheme}://localhost{port}", [name, tgt]


def finish_plan(out, plan, blockers, fixes, notes, changes, risks):
    verdict = "not_here" if blockers else ("fix_first" if fixes else "ready")
    minutes = None
    if verdict != "not_here":
        gb_dl = (plan.get("download_gb") or 0) + plan.get("size_unknown", 0) * 1.0
        minutes = int(gb_dl * 1024 / MB_PER_S / 60) + BUILD_MIN * len(plan.get("builds", [])) + START_MIN
    kinds = {b["kind"] for b in blockers}
    if verdict == "not_here":
        if kinds == {"project"}:
            recommend = "static"  # 项目本身的问题，换台机器也一样
        else:
            recommend = "handoff" if plan.get("sandbox") or kinds - {"project"} <= {"network"} else "recheck"
    else:
        recommend = "run"
    plan.update({"verdict": verdict, "blockers": [b["msg"] for b in blockers], "blocker_kinds": sorted(kinds),
                 "fixes": fixes, "notes": notes, "changes": changes, "risks": risks, "estimate_min": minutes,
                 "recommend": recommend})
    (out / "run").mkdir(exist_ok=True)
    (out / "run" / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    card = render_card(plan)
    (out / "run" / "plan.md").write_text(card, encoding="utf-8")
    print(card)
    sys.exit({"ready": 0, "fix_first": 2, "not_here": 3}[verdict])


def render_card(p):
    repo = p.get("repo") or ""
    name = repo.split("/")[-1] if repo and repo != "local" else (Path(p.get("src") or p.get("out") or "").name or "该项目")
    L = [f"## 运行决策：要把 {name} 跑起来截图吗？", "",
         "截图能把功能清单里只见于代码或文档的功能（🔍 / ❓）用界面坐实为 ✅；不运行也能完成静态分析。", ""]
    head = {"ready": f"**结论：可以在这台机器上运行**（预计 {p['estimate_min']} 分钟）",
            "fix_first": f"**结论：处理完下面 {len(p['fixes'])} 件事后可以运行**（预计 {p['estimate_min']} 分钟）",
            "not_here": "**结论：当前环境跑不起来这个项目**"}[p["verdict"]]
    L += [head, ""]
    for x in p["blockers"]:
        L.append(f"- 无法运行：{x}")
    for x in p["fixes"]:
        L.append(f"- 需先处理：{x}")
    for x in p["notes"]:
        L.append(f"- 注意：{x}")
    if p["blockers"] or p["fixes"] or p["notes"]:
        L.append("")
    if p.get("risks") and p["verdict"] != "not_here":
        L += ["**⚠ 这个项目要求较高的主机权限**（容器能接触到容器以外的东西，请确认可以接受）：", ""]
        L += [f"- {r}" for r in p["risks"]] + [""]
    if p.get("services"):
        imgs = p.get("images", [])
        uniq = len({x["image"] for x in imgs})
        cnt = lambda st: len({x["image"] for x in imgs if x.get("status") == st})
        local, dead = cnt("本地已有"), cnt("仓库不可访问")
        parts = []
        if p.get("to_pull"):
            parts.append(f"需下载 {p['to_pull']} 个，" + (f"约 {p['download_gb']} GB" if p.get("download_gb") else "大小未知")
                         + (f"（另有 {p['size_unknown']} 个大小未知）" if p.get("download_gb") and p.get("size_unknown") else ""))
        if dead:
            parts.append(f"{dead} 个不在本地且仓库访问不了")
        if local:
            parts.append(f"{local} 个本地已有")
        if cnt("未知（Docker 未运行）"):
            parts.append("Docker 启动后确认是否需要下载")
        dl = "全部已在本地，无需下载" if imgs and local == uniq else ("；".join(parts) or "无")
        if p.get("builds"):
            dl += f"；另有 {len(p['builds'])} 个需现场构建"
        res = p.get("resources", {})
        req = res.get("required", {})
        unit = {"cpu": ("CPU ≥ ", " 核"), "mem": ("内存 ≥ ", " GB"), "disk": ("磁盘 ≥ ", " GB")}
        reqs = "、".join(unit[k][0] + f"{v:g}" + unit[k][1] for k, v in req.items()) or "文档未写明"
        url = p.get("url") or ("运行后自动识别（端口随机分配）" if p.get("web") else "未识别，运行后只能启动、无法截图")
        L += ["| 项目 | 情况 |", "|---|---|",
              f"| 启动方式 | {p.get('compose')}（共 {len(p['services'])} 个服务） |",
              f"| Docker | {p.get('docker', '—')} |",
              f"| 镜像 | {uniq} 个：{dl} |",
              f"| 本机资源 | {res.get('cpu')} 核 / {res.get('mem_gb')} GB 内存 / 可用磁盘 {res.get('disk_gb')} GB；项目要求：{reqs} |",
              f"| 占用端口 | {'、'.join(p.get('ports') or []) or '无'} |",
              f"| 访问地址 | {url} |", ""]
    L += ["**请选择：**", ""]
    if p["verdict"] == "not_here":
        if p["recommend"] == "static":
            L += ["1. **只做静态分析，跳过运行**：报告里注明未运行验证；需要时可按项目文档在容器里手动启动"]
        elif p["recommend"] == "handoff":
            L += ["1. **交给你电脑上的 Agent 运行（推荐）**：我生成一句接力指令，你发给电脑上的 WorkBuddy / Codex / Claude Code，"
                  "它会在你的电脑上给出同样的运行卡片，你再选一次即可",
                  "2. **只做静态分析，跳过运行**：报告里注明未运行验证"]
        else:
            L += ["1. **我处理好了，重新检查**：按上面「无法运行」处理后选这个（如安装并打开 OrbStack / Docker Desktop、清理磁盘）",
                  "2. **交给另一台电脑上的 Agent 运行**：我生成一句接力指令，你发给那台电脑上的 WorkBuddy / Codex / Claude Code",
                  "3. **只做静态分析，跳过运行**：报告里注明未运行验证"]
        return "\n".join(L) + "\n"
    shots = "按功能清单截图" if (p.get("url") or p.get("web")) else "（未识别网页地址，可能无法截图）"
    body = f"拉取镜像、启动、等服务就绪、{shots}，结束后自动停止并删除本次的容器、网络和数据卷（镜像保留）"
    if p["verdict"] == "fix_first":
        first = f"1. **我处理好了{'，也接受上述权限' if p.get('risks') else ''}，开始运行**：处理完上面的事项后选这个，我会重新检查一遍再运行；运行时{body}"
    elif p.get("risks"):
        first = f"1. **我了解上述权限，在这台机器上运行**：{body}"
    else:
        first = f"1. **在这台机器上运行并截图（推荐）**：{body}"
    L += [first, "2. **只做静态分析，跳过运行**"]
    if p["changes"]:
        L += ["", "选 1 时会对系统做的改动：" + "；".join(p["changes"]) + "。"]
    L += ["", "安全边界：项目在容器里运行" + ("（上面列出的权限除外）" if p.get("risks") else "") + "，用的是 run/work 下的项目副本，不改原项目；只用项目默认配置和本地初始化的管理员账号，"
              "不填任何真实密钥；全程限时，超时自动停止并清理。"]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- run
ADVICE = [
    (r"exited with code 137|OOMKilled|out of memory|Cannot allocate memory", "内存不够，容器被系统杀掉：在 OrbStack / Docker Desktop 里调大内存上限，或关闭其他占内存的程序"),
    (r"max virtual memory areas vm.max_map_count|max_map_count", "Elasticsearch 要求 vm.max_map_count ≥ 262144，自动调整没有生效（Docker 重启过会恢复默认值）：重新运行一次"),
    (r"port is already allocated|address already in use", "端口被占用：关掉占用端口的程序，或改项目 .env 里的端口"),
    (r"no space left on device", "磁盘空间不足：清理磁盘，或用 docker rmi 删除不再需要的镜像"),
    (r"toomanyrequests|rate limit", "Docker Hub 匿名下载次数用完了：过一小时再试，或在 Docker 里登录 Docker Hub 账号、配置镜像加速"),
    (r"no matching manifest|exec format error", "镜像没有本机架构版本，需要按 x86 转译运行（脚本会自动处理；若仍失败，说明转译不可用）"),
    (r"pull access denied|manifest unknown|not found: manifest", "镜像不存在或需要登录：检查项目 .env 里的镜像名和版本"),
    (r"Conflict\. The container name|is already in use by container", "已有同名容器：先停止并删除那个容器，或确认不再需要后让我处理"),
    (r"executable file not found|no such file or directory: unknown", "容器里找不到要执行的程序：多半是镜像版本和 compose 文件不匹配，检查 .env 里的镜像版本"),
    (r"TLS handshake timeout|i/o timeout|connection refused|dial tcp|net/http: request canceled|failed to do request|Forbidden", "下载镜像时网络不通或太慢：检查网络、代理或镜像加速设置"),
    (r"permission denied while trying to connect to the Docker daemon", "当前用户没有权限访问 Docker：把用户加入 docker 组，或用有权限的账号运行"),
]


def advise(text):
    for pat, tip in ADVICE:
        if re.search(pat, text or "", re.I):
            return tip
    return None


def write_override(out, services):
    lines = ["# repo-dissect 生成：为只有 x86 镜像的服务指定平台，不改项目文件", "services:"]
    for s in sorted(set(services)):
        lines += [f"  {s}:", "    platform: linux/amd64"]
    (out / "run" / "compose.override.yml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def ps_states(plan, out):
    code, o, _ = sh(compose_cmd(plan, out, ["ps", "-a", "--format", "json"]), timeout=30)
    o = o.strip()
    if code or not o:
        return []
    data = jloads(o)
    if data is None:
        data = [x for x in (jloads(ln) for ln in o.splitlines() if ln.strip().startswith("{")) if x]
    return data if isinstance(data, list) else [data]


def resolve_url(plan, out):
    """端口随机分配时，每次运行都用 docker compose port 查实际端口（不写回 plan，避免下次用到旧端口）"""
    if plan.get("url") or not plan.get("web"):
        return plan.get("url")
    svc, tgt = plan["web"]
    code, o, _ = sh(compose_cmd(plan, out, ["port", svc, str(tgt)]), timeout=20)
    m = re.search(r":(\d+)\s*$", o.strip()) if code == 0 else None
    if m:
        return f"{'https' if tgt == 443 else 'http'}://localhost:{m.group(1)}"
    return None


def dump_logs(plan, out, services, log):
    names = []
    for svc in services:
        _, lo, le = sh(compose_cmd(plan, out, ["logs", "--no-color", "--tail", "80", svc]), timeout=60)
        if (lo + le).strip():
            (out / "run" / f"logs-{svc}.txt").write_text(lo + le, encoding="utf-8")
            names.append(f"run/logs-{svc}.txt")
    if names:
        log("已保存日志：" + "、".join(names))
    return names


def raise_map_count(plan, out, log):
    mode = plan.get("sysctl")
    if mode == "host":
        cur = max_map_count_host()
        if cur is not None and cur < 262144:
            pre = [] if (hasattr(os, "geteuid") and os.geteuid() == 0) else ["sudo", "-n"]
            code, o, e = sh(pre + ["sysctl", "-w", "vm.max_map_count=262144"], timeout=30)
            log("已把 vm.max_map_count 调到 262144" if code == 0 else f"调整 vm.max_map_count 失败（{(e or o).strip()[:120]}），继续尝试")
    elif mode == "vm":
        if not local_image("busybox:1.36"):
            sh(["docker", "pull", "busybox:1.36"], timeout=180)
        code, o, e = sh(["docker", "run", "--rm", "--privileged", "busybox:1.36", "sh", "-c",
                         'v=$(cat /proc/sys/vm/max_map_count); [ "$v" -ge 262144 ] || sysctl -w vm.max_map_count=262144 >/dev/null; '
                         'cat /proc/sys/vm/max_map_count'], timeout=120)
        log(f"Docker 虚拟机的 vm.max_map_count = {o.strip()}" if code == 0 else
            f"调整 vm.max_map_count 失败（{(e or o).strip()[:120]}），继续尝试")


def cmd_run(out, args):
    plan_p = out / "run" / "plan.json"
    if not plan_p.is_file():
        sys.exit("还没有运行计划：先执行 plan，给用户看决策卡片并得到同意")
    plan = json.loads(plan_p.read_text(encoding="utf-8"))
    if plan["verdict"] == "not_here":
        sys.exit("plan 的结论是当前环境跑不起来；请改用 handoff 交给用户电脑上的 Agent，或只做静态分析")
    if plan["verdict"] == "fix_first":
        print("提示：plan 列出的待处理事项可能还没处理，继续尝试运行；失败时会给出原因")
    for old in ("run.log", "result.json"):
        if (out / "run" / old).exists():
            (out / "run" / old).unlink()
    log = Log(out / "run" / "run.log")
    tmin = float(args.get("timeout_min", 25))
    deadline = time.time() + tmin * 60
    t_start = time.time()
    result = {"status": "failed", "url": plan.get("url"), "project": plan["project"],
              "started": datetime.datetime.now().isoformat(timespec="seconds")}

    def fail(reason, detail="", logs_of=None):
        if logs_of:
            result["logs"] = dump_logs(plan, out, logs_of, log)
        tip = advise(detail) or advise(reason)
        key = [ln.strip() for ln in (detail or "").splitlines() if re.search(r"error|fail|denied|refused|killed", ln, re.I)]
        tail = "\n".join((key or (detail or "").strip().splitlines())[-6:])[-1200:]
        log(f"运行失败：{reason}" + (f"；建议：{tip}" if tip else ""))
        if tail:
            log("关键输出：\n" + tail)
        result.update({"status": "failed", "reason": reason, "advice": tip, "detail": tail,
                       "minutes": round((time.time() - t_start) / 60, 1)})
        save_result(out, result)
        if not args.get("keep") and daemon_up():
            cleanup(out, plan, log)
            result["cleaned"] = True
        result["finished"] = True
        save_result(out, result)
        log("结束（失败）")
        sys.exit(1)

    if not start_daemon(log):
        fail("Docker 没有启动起来", "permission denied while trying to connect to the Docker daemon"
             if daemon_state() == "denied" else "")
    prepare_work(Path(plan["src"]), Path(plan["work"]), log)
    prepare_env(Path(plan["compose_work"]).parent)
    if plan.get("need_amd64"):
        write_override(out, plan["need_amd64"])
    info = docker_info()
    builds = set(plan.get("builds") or [])
    missing = [s for s, d in plan["services"].items() if d.get("image") and s not in builds and not local_image(d["image"])]
    hosts = {image_ref(plan["services"][s]["image"])[0] for s in missing}
    dead = sorted(h for h in hosts if not registry_reachable(h) and not (daemon_has_mirror(info) and h == "registry-1.docker.io"))
    if dead:
        fail("镜像不在本地，且访问不了镜像仓库：" + "、".join(dead), "dial tcp: i/o timeout")
    if missing:
        log(f"拉取 {len(missing)} 个服务的镜像（体积大时需要较长时间）…")
    for attempt in (1, 2):
        if not missing:
            break
        code, o, e = sh(compose_cmd(plan, out, ["pull"] + missing), timeout=max(60, int(deadline - time.time())))
        if code == 0:
            break
        txt = o + e
        if attempt == 1 and "no matching manifest" in txt:
            extra = [s for s in missing if re.search(rf"\b{re.escape(s)}\b.*no matching manifest", txt)] or missing
            write_override(out, (plan.get("need_amd64") or []) + extra)
            log(f"部分镜像没有本机架构版本，改为按 x86 运行：{'、'.join(extra)}，重试拉取")
            continue
        fail("拉取镜像失败", txt[-2000:])
    if plan.get("sysctl"):
        raise_map_count(plan, out, log)
    log("启动服务…" + ("（包含现场构建，时间较长）" if builds else ""))
    code, o, e = sh(compose_cmd(plan, out, ["up", "-d"]), timeout=max(120, int(deadline - time.time())))
    if code:
        fail("启动失败", (o + e)[-2000:], logs_of=list(plan["services"]))
    t_up = time.time()
    log("等待服务就绪…")
    ready, last, unhealthy_since = False, "", {}
    while time.time() < deadline:
        st = ps_states(plan, out)
        bad = [s for s in st if s.get("State") in ("exited", "dead") and int(s.get("ExitCode") or 0) != 0]
        restarting = [s for s in st if s.get("State") == "restarting"]
        if bad or (restarting and time.time() - t_up > 180):
            svc = (bad or restarting)[0].get("Service")
            _, lo, le = sh(compose_cmd(plan, out, ["logs", "--no-color", "--tail", "80", svc]), timeout=60)
            fail(f"服务 {svc} 启动后{'退出' if bad else '反复重启'}（日志见 run/logs-{svc}.txt）", lo + le, logs_of=[svc])
        now = time.time()
        for s in st:
            if s.get("Health") == "unhealthy":
                unhealthy_since.setdefault(s.get("Service"), now)
            else:
                unhealthy_since.pop(s.get("Service"), None)
        stuck = [k for k, t0 in unhealthy_since.items() if now - t0 > 180]
        if stuck:
            fail(f"服务 {stuck[0]} 健康检查持续失败超过 3 分钟（日志见 run/logs-{stuck[0]}.txt）", "", logs_of=stuck)
        waiting = [s.get("Service") for s in st
                   if (s.get("State") != "running" and not (s.get("State") == "exited" and int(s.get("ExitCode") or 0) == 0))
                   or s.get("Health") in ("starting", "unhealthy")]
        url = args.get("base") or resolve_url(plan, out)
        url_ok = True
        if url:
            c, _, _ = http(url, timeout=5)
            url_ok = 0 < c < 500
        msg = (f"运行中 {sum(1 for s in st if s.get('State') == 'running')}/{len(st)}，等待：{'、'.join(waiting) or '—'}，"
               + (f"网页 {url} {'可访问' if url_ok else '暂不可访问'}" if url else "未识别网页地址"))
        if msg != last:
            log(msg)
            last = msg
        if st and not waiting and url_ok:
            ready = True
            break
        time.sleep(8)
    if not ready:
        st = ps_states(plan, out)
        slow = [s.get("Service") for s in st if s.get("State") != "running" or s.get("Health") in ("starting", "unhealthy")]
        fail(f"超过 {tmin:g} 分钟仍未就绪（{last}）", "", logs_of=slow or list(plan["services"]))
    url = args.get("base") or resolve_url(plan, out)
    mins = round((time.time() - t_start) / 60, 1)
    log(f"项目已就绪：{url or '（未识别网页地址）'}，用时 {mins} 分钟")
    result.update({"status": "ready", "minutes": mins, "url": url})
    save_result(out, result)
    pages = args.get("pages") or ((out / "run" / "pages.json").is_file() and str(out / "run" / "pages.json"))
    if url:
        shots = screenshot(out, url, load_pages(pages) if pages else [{"name": "00-首页", "path": "/"}],
                           login_arg(args), log)
        result["screens"] = shots
        if not shots:
            result["screens_skipped"] = "截图没有成功，见 run.log"
    else:
        log("未识别网页地址，跳过截图；如果项目有网页，用 --base 指定地址后执行 screenshot")
        result["screens_skipped"] = "未识别网页地址"
    save_result(out, result)
    if args.get("keep"):
        log(f"按 --keep 保留运行；用完执行：python3 run_project.py cleanup {out}")
    else:
        cleanup(out, plan, log)
        result["cleaned"] = True
    result["finished"] = True
    save_result(out, result)
    log("结束（成功）")


def save_result(out, result):
    (out / "run" / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def login_arg(args):
    return args.get("login") or os.environ.get("RD_LOGIN")


# ---------------------------------------------------------------- screenshot
def load_pages(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["pages"] if isinstance(data, dict) else data


def settle(page, ms=15000):
    """等页面网络安静；一直有轮询请求的页面不会安静，超时就算了"""
    try:
        page.wait_for_load_state("networkidle", timeout=ms)
    except Exception:
        pass


def screenshot(out, base, pages, login, log):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("没有安装 Python playwright，跳过截图（可 pip install playwright && python -m playwright install chromium）")
        return []
    shots_dir = out / "img" / "screens"
    shots_dir.mkdir(parents=True, exist_ok=True)
    done = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-proxy-server"] if is_local_url(base) else [])
            ctx = browser.new_context(viewport={"width": 1440, "height": 900}, ignore_https_errors=True)
            page = ctx.new_page()
            if login:
                user, _, pw = login.partition(":")
                try:
                    page.goto(base, wait_until="load", timeout=60000)
                    settle(page)
                    u = page.locator("input[type=email], input[name*=email i], input[name*=user i], input[type=text]").first
                    u.fill(user, timeout=10000)
                    page.locator("input[type=password]").first.fill(pw, timeout=10000)
                    try:
                        with page.expect_navigation(timeout=15000):
                            page.keyboard.press("Enter")
                    except Exception:
                        pass  # 单页应用登录不一定跳转
                    settle(page)
                    pwd = page.locator("input[type=password]")
                    still = pwd.count() and pwd.first.is_visible()
                    log("登录后仍停留在登录页，可能没有登录成功；需要时由 Agent 手动登录后再截" if still else "已登录")
                except Exception as e:
                    log(f"自动登录没有成功（{type(e).__name__}），继续截图；需要时由 Agent 手动登录后再截")
            for i, pg in enumerate(pages, 1):
                name = re.sub(r"[\\/:*?\"<>|]", "_", pg.get("name") or f"{i:02d}")
                path = pg.get("path", "/")
                url = path if path.startswith("http") else base.rstrip("/") + "/" + path.lstrip("/")
                try:
                    resp = None
                    for attempt in (1, 2):
                        try:
                            resp = page.goto(url, wait_until="load", timeout=60000)
                            break
                        except Exception:
                            if attempt == 2:
                                raise
                            page.wait_for_timeout(2000)
                    settle(page)
                    page.wait_for_timeout(int(pg.get("wait_ms", 1500)))
                    page.screenshot(path=str(shots_dir / f"{name}.png"), full_page=True)
                    (shots_dir / f"{name}.txt").write_text(page.inner_text("body")[:5000], encoding="utf-8")
                    status = resp.status if resp else None
                    item = {"name": name, "url": url, "file": f"img/screens/{name}.png", "http": status}
                    if status and status >= 400:
                        item["warning"] = f"页面返回 HTTP {status}，截图不能当作功能存在的证据"
                    elif i > 1 or path not in ("", "/"):
                        pwd = page.locator("input[type=password]")
                        if pwd.count() and pwd.first.is_visible() and \
                                not re.search(r"login|signin|sign-in|登录|注册|register", name + url, re.I):
                            item["warning"] = "页面显示的是登录框，可能没登录或已掉线，截图不能当作该功能的证据"
                    done.append(item)
                    log(f"已截图：{name}（{url}）" + (f"，注意：{item['warning']}" if item.get("warning") else ""))
                except Exception as e:
                    first = str(e).splitlines()[0][:160] if str(e) else ""
                    log(f"截图失败：{name}（{url}）：{type(e).__name__}: {first}")
            browser.close()
    except Exception as e:
        log(f"浏览器启动失败（{type(e).__name__}: {str(e)[:120]}），跳过截图")
    return done


def cmd_screenshot(out, args):
    if not args.get("pages") and (out / "run" / "pages.json").is_file():
        args["pages"] = str(out / "run" / "pages.json")
    if not args.get("pages"):
        sys.exit("需要 --pages pages.json，格式：[{\"name\": \"01-知识库列表\", \"path\": \"/knowledge\"}]")
    base = args.get("base")
    if not base:
        pp = out / "run" / "plan.json"
        plan = jloads(pp.read_text(encoding="utf-8"), {}) if pp.is_file() else {}
        if plan.get("compose_work") and daemon_up():
            base = resolve_url(plan, out)  # 运行中的实际地址（随机端口也能查到）
    if not base:
        sys.exit("不知道项目地址：用 --base 指定，例如 --base http://localhost")
    log = Log(out / "run" / "run.log")
    done = screenshot(out, base, load_pages(args["pages"]), login_arg(args), log)
    print(json.dumps(done, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- cleanup / handoff
def cleanup(out, plan, log):
    """只删本次项目名下的容器、网络、数据卷。不用 down -v：它会连同 compose 里用 name: 指向的已有数据卷一起删"""
    log("清理：停止并删除本次启动的容器和网络…")
    # rm -v 只删容器上的匿名卷（镜像里 VOLUME 声明的），不碰有名字的卷
    sh(compose_cmd(plan, out, ["rm", "--stop", "--force", "-v"]), timeout=300)
    code, o, e = sh(compose_cmd(plan, out, ["down", "--remove-orphans"]), timeout=300)
    if code:
        log(f"停止容器时出错：{(e or o).strip()[-300:]}")
    _, vo, _ = sh(["docker", "volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={plan['project']}"], timeout=30)
    vols = [x for x in vo.split() if x]
    if vols:
        code, o, e = sh(["docker", "volume", "rm"] + vols, timeout=120)
        log(f"已删除本次创建的 {len(vols)} 个数据卷" if code == 0 else f"删除数据卷时出错：{(e or o).strip()[-200:]}")
    work = Path(plan.get("work") or out / "run" / "work")
    if work.exists():
        shutil.rmtree(str(work), ignore_errors=True)
        if work.exists():
            log(f"项目副本里有容器写入的文件（属于管理员）删不掉，可手动删除：{work}")
    imgs = sorted({i["image"] for i in plan.get("images", []) if i.get("status") == "需下载"})
    log("清理完成。下载的镜像保留以便下次直接运行" + (f"；不需要时执行 docker rmi {' '.join(imgs)}" if imgs else ""))


def cmd_cleanup(out, args):
    plan_p = out / "run" / "plan.json"
    if not plan_p.is_file():
        sys.exit("没有 run/plan.json，不清楚要清理哪个项目")
    plan = json.loads(plan_p.read_text(encoding="utf-8"))
    if not plan.get("compose_work"):
        sys.exit("plan 里没有启动方式，没有需要清理的容器")
    if not daemon_up():
        sys.exit("Docker 没有运行，没有需要清理的容器")
    cleanup(out, plan, Log(out / "run" / "run.log"))


def cmd_handoff(out, args):
    v = load_vars(out)
    repo, sha = v.get("REPO", ""), v.get("SHA", "")
    name = (repo.split("/")[-1] if repo and repo != "local" else out.name)
    url = f"https://github.com/{repo}" if repo and repo != "local" else "<仓库地址或本地路径>"
    prompt = (f"用 repo-dissect 技能为 {url} 的 commit {sha or '<sha>'} 补做第 3 节「运行与截图」，输出目录 ~/repo-dissect/{name}/："
              "先运行 run_project.py plan 给我一张运行决策卡片，我选定后由你完成运行、截图、回填功能清单并重新生成 report.html。")
    pages = out / "run" / "pages.json"
    lines = [f"# 在你的电脑上补做「运行与截图」：{name}", "",
             "当前环境跑不起来这个项目（原因见 run/plan.md）。把下面这句话发给你电脑上的 Agent"
             "（WorkBuddy / Codex / Claude Code，需已安装 repo-dissect）：", "",
             "```text", prompt, "```", "",
             "它会：检查你电脑的 Docker、内存、端口 → 给你一张运行决策卡片 → 你选一次 → 它自动下载、启动、截图、"
             "回填功能清单、重新生成报告，结束后自动清理容器。", "",
             f"把本次的结果文件夹放到你电脑的 ~/repo-dissect/{name}/，它会直接在原结果上补截图、回填功能清单；"
             "没有放的话，它只做运行和截图，把 img/screens/ 和 run/result.json 交回来，再合并到本次结果。"]
    if pages.is_file():
        lines += ["", "要截图的页面（按功能清单整理，放在 run/pages.json，对方 Agent 会直接使用）：", "",
                  "```json", pages.read_text(encoding="utf-8").strip(), "```"]
    text = "\n".join(lines) + "\n"
    (out / "run").mkdir(exist_ok=True)
    (out / "run-locally.md").write_text(text, encoding="utf-8")
    print(text)


# ---------------------------------------------------------------- 入口
def parse(argv):
    if len(argv) < 2 or argv[0] not in ("plan", "run", "screenshot", "cleanup", "handoff"):
        sys.exit(__doc__)
    cmd, out, rest = argv[0], Path(argv[1]).expanduser().resolve(), argv[2:]
    args, i = {}, 0
    while i < len(rest):
        k = rest[i].lstrip("-").replace("-", "_")
        if k == "keep":
            args["keep"] = True
            i += 1
            continue
        if i + 1 >= len(rest):
            sys.exit(f"参数 {rest[i]} 缺少值\n" + __doc__)
        args[k] = rest[i + 1]
        i += 2
    if not out.is_dir():
        sys.exit(f"输出目录不存在：{out}")
    return cmd, out, args


def main():
    utf8_stdio()
    cmd, out, args = parse(sys.argv[1:])
    {"plan": cmd_plan, "run": cmd_run, "screenshot": cmd_screenshot, "cleanup": cmd_cleanup, "handoff": cmd_handoff}[cmd](out, args)


if __name__ == "__main__":
    main()
