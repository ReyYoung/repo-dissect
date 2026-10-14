"""repo-dissect 取码：git clone 不可用或极慢时，换别的路把固定 commit 的源码拿下来，并逐文件校验。

用法（只用标准库，Python 3.8+）:
  python3 fetch_repo.py <owner/repo> <sha或tag/分支> <输出目录>            # 自动按顺序尝试
  python3 fetch_repo.py <owner/repo> <ref> <输出目录> --dry-run             # 只看规模（文件数、大小），不下载
  python3 fetch_repo.py <owner/repo> <sha> <输出目录> --from-archive x.zip  # 用户手动下载的源码包

常用选项:
  --method auto|git|tarball|cdn   默认 auto：git clone → 整包下载（codeload，单连接）→ 逐文件下载（jsDelivr / raw，带校验）
  --only DIR                      只取某个目录（可重复），大仓库先拿主要模块
  --proxy auto|none|URL           默认 auto：先用环境变量里的代理或直连；都不通或很慢时，自动试本机常见代理端口
                                  （Clash 7890/7897 等），只对本次命令生效，不改任何配置
  --mirror URL                    或环境变量 RD_GITHUB_MIRROR：用户自己配置的 GitHub 镜像（脚本不内置任何第三方地址）
                                  写法：含 {repo}（owner/repo）或 {url}（https://github.com/owner/repo）的模板；
                                  不含占位符时当作"换域名"，即 <镜像>/<owner>/<repo>
  --max-size MB                   逐文件下载时跳过大于该值的文件（默认 5，图片模型等大文件对分析没用），0 表示不限
  --jobs N                        逐文件下载的并发连接数（默认 4，每个连接复用）

结果:
  - git 方式得到普通 git 仓库（有历史）；其他方式得到纯源码目录，
    并在 <输出目录>/.rd-manifest.json 记录 {repo, sha, source, verified, files:{路径: blob sha}}，checklinks.py 据此核验
  - 校验：拿得到 GitHub 文件清单（tree API）时，逐文件比对 git blob SHA-1；镜像来源一律靠固定 commit 核对
  - 最后一行"取码方式: …"原样写进 index.md
  - 不会关闭证书校验；证书不受信时请按 check_env.py 的提示处理
退出码: 0 成功；1 全部方式失败（会给出下一步建议）；2 参数错误
"""
import argparse
import base64
import hashlib
import http.client
import tempfile
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

for _s in (sys.stdout, sys.stderr):  # Windows 中文控制台（GBK）
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

SLOW = 5.0  # 单次 TCP+TLS 建连超过这么多秒，算"慢但可用"
LOCAL_PROXY_PORTS = [7890, 7897, 7891, 7899, 10809, 1087, 8889, 6152, 20171, 8118]
UA = "repo-dissect-fetch"


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- 网络工具（check_env.py 也用）
def env_proxy():
    for k in ("https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        v = os.environ.get(k)
        if v:
            return v
    return None


def parse_proxy(url):
    """返回 (host, port, auth头或None)；只支持 http:// 代理（标准库没有 socks）"""
    if not url:
        return None
    if "://" not in url:
        url = "http://" + url
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https"):
        return None
    auth = None
    if u.username:
        cred = f"{urllib.parse.unquote(u.username)}:{urllib.parse.unquote(u.password or '')}"
        auth = "Basic " + base64.b64encode(cred.encode()).decode()
    return u.hostname, u.port or 80, auth


def _connect(host, port, proxy, timeout):
    """直连或经 http 代理 CONNECT 打通到 host:port 的 TCP 连接"""
    p = parse_proxy(proxy) if proxy else None
    if proxy and not p:
        raise OSError(f"不支持的代理写法 {proxy}（只支持 http://，socks 代理请改用它的 http 端口）")
    if not p:
        return socket.create_connection((host, port), timeout)
    s = socket.create_connection((p[0], p[1]), timeout)
    req = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n"
    if p[2]:
        req += f"Proxy-Authorization: {p[2]}\r\n"
    s.sendall((req + "\r\n").encode())
    buf = b""
    while b"\r\n\r\n" not in buf and len(buf) < 65536:
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    first = buf.split(b"\r\n", 1)[0].decode("latin-1", "replace")
    if not re.match(r"HTTP/\d(\.\d)?\s+200", first):
        s.close()
        raise OSError(f"代理拒绝连接：{first or '无响应'}")
    return s


def tls_probe(host="github.com", proxy=None, timeout=10):
    """量一次 TCP+TLS 建连耗时，并检查证书是否受信。返回 {ok, secs, cert, error}"""
    t0 = time.monotonic()
    try:
        s = _connect(host, 443, proxy, timeout)
        s.settimeout(timeout)
        ss = ssl.create_default_context().wrap_socket(s, server_hostname=host)
        ss.close()
        return {"ok": True, "secs": time.monotonic() - t0, "cert": True, "error": ""}
    except ssl.SSLCertVerificationError as e:
        return {"ok": False, "secs": time.monotonic() - t0, "cert": False, "error": e.verify_message or str(e)}
    except Exception as e:
        return {"ok": False, "secs": time.monotonic() - t0, "cert": None, "error": f"{type(e).__name__}: {e}"}


def port_open(host, port, timeout=0.5):
    try:
        socket.create_connection((host, port), timeout).close()
        return True
    except OSError:
        return False


def local_proxies(host="github.com", timeout=6):
    """本机开着、并且能 CONNECT 到 host 的 http 代理端口（Clash 的混合端口同时支持 http）"""
    found = []
    for port in LOCAL_PROXY_PORTS:
        if not port_open("127.0.0.1", port):
            continue
        url = f"http://127.0.0.1:{port}"
        r = tls_probe(host, url, timeout)
        if r["ok"]:
            found.append((url, r["secs"]))
    return found


def git_proxy_keys():
    """git 配置里生效的代理项：http.proxy 和针对 GitHub 的 http.<url>.proxy（git 不读 https.proxy）"""
    try:
        r = subprocess.run(["git", "config", "--get-regexp", r"^http\..*proxy$"], capture_output=True, timeout=5)
    except Exception:
        return []
    out = []
    for ln in r.stdout.decode("utf-8", "replace").splitlines():
        k, _, v = ln.partition(" ")
        kl = k.lower()
        if kl == "http.proxy" or (kl.endswith(".proxy") and "github" in kl):
            out.append((k, v.strip()))
    return out


def git_proxy_config():
    """git 配置里的代理（只看 git 真正会用的 http.proxy / http.<GitHub 地址>.proxy），没有则 None"""
    keys = git_proxy_keys()
    return keys[0] if keys else None


def proxy_alive(url):
    p = parse_proxy(url)
    if not p:  # socks 等：只看端口
        u = urllib.parse.urlsplit(url if "://" in url else "http://" + url)
        return bool(u.hostname and u.port and port_open(u.hostname, u.port, 1.5))
    return port_open(p[0], p[1], 1.5)


def choose_route(proxy_arg, host="github.com", quiet=False):
    """决定本次走直连还是哪个代理。返回 (proxy或None, probe结果, 说明)"""
    if proxy_arg not in (None, "auto"):
        px = None if proxy_arg == "none" else proxy_arg
        r = tls_probe(host, px)
        return px, r, ("直连" if not px else f"指定代理 {px}")
    candidates = []
    ep = env_proxy()
    if ep and parse_proxy(ep):
        candidates.append((ep, "环境变量代理"))
    candidates.append((None, "直连"))  # 环境变量里的代理失效时也试一下直连
    best = None
    for px, why in candidates:
        r = tls_probe(host, px)
        if r["ok"] and r["secs"] <= SLOW:
            return px, r, why
        if r["ok"]:
            best = best or (px, r, why)
        elif r["cert"] is False:  # 证书问题换代理也没用，直接返回让上层提示
            return px, r, why
    if not quiet:
        log("· 连 github.com " + (f"较慢（{best[1]['secs']:.1f} 秒）" if best else "不通") + "，试试本机代理端口…")
    for url, secs in local_proxies(host):
        if not best or secs < best[1]["secs"]:
            return url, {"ok": True, "secs": secs, "cert": True, "error": ""}, f"本机代理 {url}，只对本次命令生效"
    if best:
        return best
    px, why = candidates[0]
    return px, tls_probe(host, px), why


def opener(proxy):
    return urllib.request.build_opener(urllib.request.ProxyHandler({"https": proxy, "http": proxy} if proxy else {}))


def gh_token():
    for k in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(k):
            return os.environ[k]
    if shutil.which("gh"):
        try:
            r = subprocess.run(["gh", "auth", "token"], capture_output=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.decode().strip()
        except Exception:
            pass
    return None


def api_get(path, proxy, accept="application/vnd.github+json", timeout=30):
    req = urllib.request.Request("https://api.github.com" + path, headers={"Accept": accept, "User-Agent": UA})
    tok = gh_token()
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    with opener(proxy).open(req, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------- 校验与清单
def blob_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


WIN_RESERVED = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$", re.I)


def safe_rel(path):
    """仓库内相对路径：拒绝绝对路径、..、空段、控制字符；Windows 上再拒绝盘符冒号、保留名和非法字符，
    防止写到输出目录外"""
    p = path.replace("\\", "/")
    if not p or p.startswith("/") or re.search(r"[\x00-\x1f]", p):
        return None
    parts = p.split("/")
    if any(x in ("", ".", "..") for x in parts):
        return None
    if os.name == "nt" and any(re.search(r'[:<>"|?*]', x) or WIN_RESERVED.match(x) or x.endswith((".", " "))
                               for x in parts):
        return None
    return "/".join(parts)


def dest_path(out, rel):
    """rel 对应的磁盘路径；再确认一次它确实在 out 里面"""
    dest = os.path.join(out, *rel.split("/"))
    root = os.path.realpath(out)
    if not os.path.realpath(dest).startswith(root + os.sep):
        raise ValueError(f"路径越界：{rel}")
    return dest


def in_scope(path, only):
    return not only or any(path == d or path.startswith(d.rstrip("/") + "/") for d in only)


def resolve_sha(repo, ref, proxy, git_url=None):
    """tag/分支 → 40 位 commit。优先问 GitHub API；不通时用 git ls-remote。返回 (sha, 来源)"""
    if re.fullmatch(r"[0-9a-f]{40}", ref):
        return ref, "given"
    try:
        sha = api_get(f"/repos/{repo}/commits/{urllib.parse.quote(ref, safe='')}", proxy,
                      accept="application/vnd.github.sha").decode().strip()
        if re.fullmatch(r"[0-9a-f]{40}", sha):
            return sha, "api"
    except Exception:
        pass
    url = git_url or f"https://github.com/{repo}.git"
    want = ["HEAD"] if ref == "HEAD" else [f"refs/tags/{ref}", f"refs/tags/{ref}^{{}}", f"refs/heads/{ref}"]
    try:
        r = subprocess.run(git_cmd(proxy) + ["ls-remote", url] + want, capture_output=True, timeout=120, env=git_env(proxy))
        refs = dict((n, sha_) for sha_, n in (ln.split("\t", 1) for ln in r.stdout.decode().splitlines() if "\t" in ln))
        # 只认完全同名的引用：附注 tag 指向的 commit > tag > 分支
        for k in ([f"refs/tags/{ref}^{{}}", f"refs/tags/{ref}", f"refs/heads/{ref}"] if ref != "HEAD" else ["HEAD"]):
            if k in refs:
                return refs[k], ("mirror" if git_url else "ls-remote")
    except Exception:
        pass
    return None, None


TRUNCATED = [False]  # GitHub 文件清单是否被截断（文件太多时）


def get_tree(repo, sha, proxy):
    """GitHub tree API：{path: (blob sha, size, mode)}；拿不到返回 None"""
    try:
        data = json.loads(api_get(f"/repos/{repo}/git/trees/{sha}?recursive=1", proxy, timeout=60))
    except Exception as e:
        why = f"HTTP {e.code}" if isinstance(e, urllib.error.HTTPError) else type(e).__name__
        log(f"· 拿不到 GitHub 文件清单（{why}），下载后无法逐文件对照官方清单")
        return None
    if data.get("truncated"):
        TRUNCATED[0] = True
        log("· 仓库文件太多，GitHub 文件清单被截断；只对清单内的文件做校验，逐文件下载也只能拿到清单内的文件")
    tree = {}
    for e in data.get("tree", []):
        if e.get("type") == "blob":
            p = safe_rel(e["path"])
            if p:
                tree[p] = (e["sha"], e.get("size", 0), e.get("mode", ""))
    return tree


def write_manifest(out, repo, sha, source, files, verified, skipped, notes):
    m = {"repo": repo, "sha": sha, "source": source, "verified": verified,
         "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "files": files,
         "skipped": skipped, "notes": notes}
    with open(os.path.join(out, ".rd-manifest.json"), "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- 方式一：git clone
def git_cmd(proxy):
    """只对本次命令设置代理（不改用户配置）：覆盖 http.proxy 和针对 GitHub 的代理项，绕开失效的全局代理"""
    cmd = ["git", "-c", f"http.proxy={proxy or ''}"]
    for k, _ in git_proxy_keys():
        if k.lower() != "http.proxy":
            cmd += ["-c", f"{k}={proxy or ''}"]
    return cmd + ["-c", "http.lowSpeedLimit=1000", "-c", "http.lowSpeedTime=60"]


def git_env(proxy):
    """git 在配置为空时会退回读环境变量里的代理：直连时把它们去掉，走代理时统一成选定的那个"""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    for k in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        env.pop(k, None)
    if proxy:
        env["https_proxy"] = env["http_proxy"] = proxy
    return env


def via_git(url, sha, out, proxy, timeout, label):
    log(f"· 方式：git clone（{label}）")
    env = git_env(proxy)
    t0 = time.monotonic()

    def step(args, t):
        left = timeout - (time.monotonic() - t0)
        if left <= 5:
            raise TimeoutError("超过时间盒")
        r = subprocess.run(git_cmd(proxy) + args, capture_output=True, timeout=min(t, left), env=env)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).decode("utf-8", "replace").strip().splitlines()[-1:] or ["失败"])
        return r

    try:
        step(["clone", "--filter=blob:none", "--no-checkout", "--quiet", url, out], timeout)
        if subprocess.run(["git", "-C", out, "cat-file", "-e", sha + "^{commit}"], capture_output=True).returncode != 0:
            step(["-C", out, "fetch", "--quiet", "--filter=blob:none", "origin", sha], timeout)
        step(["-C", out, "checkout", "--quiet", "--detach", sha], timeout)
        head = subprocess.run(["git", "-C", out, "rev-parse", "HEAD"], capture_output=True).stdout.decode().strip()
        if head != sha:
            raise RuntimeError(f"检出的 commit {head[:12]} 与 {sha[:12]} 不一致")
        return True
    except (subprocess.TimeoutExpired, TimeoutError):
        log(f"  ✗ git clone {timeout} 秒内没完成，换下一种方式")
    except Exception as e:
        msg = e.args[0] if e.args else e
        log(f"  ✗ git clone 失败：{msg[0] if isinstance(msg, list) and msg else msg}")
    return False


# ---------------------------------------------------------------- 方式二：整包（tar.gz / zip）
def extract_archive(fobj, kind, out, only):
    """安全解包到 out：去掉顶层目录；跳过越界路径；符号链接写成内容为目标路径的普通文件（与 git 的 blob 一致）。
    返回 ({path: blob sha}, 包里记录的 commit 或 None, 跳过的说明列表)"""
    files, skipped, commit = {}, [], None

    def put(rel, data):
        dest = dest_path(out, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)
        files[rel] = blob_sha(data)

    if kind == "tar":
        tf = tarfile.open(fileobj=fobj, mode="r:*")
        for m in tf:
            parts = m.name.replace("\\", "/").split("/", 1)
            if len(parts) < 2 or not parts[1]:
                continue
            rel = safe_rel(parts[1].rstrip("/"))
            if not rel:
                skipped.append(f"{m.name}（路径不安全）")
                continue
            if m.isdir() or not in_scope(rel, only):
                continue
            if m.issym():
                put(rel, m.linkname.encode("utf-8", "surrogateescape"))
            elif m.isfile():
                put(rel, tf.extractfile(m).read())
            else:
                skipped.append(f"{rel}（硬链接或特殊文件）")
        commit = (tf.pax_headers or {}).get("comment")  # GitHub 整包的全局头里记着 commit
    else:
        zf = zipfile.ZipFile(fobj)
        c = zf.comment.decode("ascii", "ignore").strip()
        commit = c if re.fullmatch(r"[0-9a-f]{40}", c) else None
        names = [n for n in zf.namelist() if not n.endswith("/")]
        tops = {n.split("/", 1)[0] for n in zf.namelist()}
        strip = len(tops) == 1 and all("/" in n for n in names)
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.split("/", 1)[1] if strip else info.filename
            rel = safe_rel(name)
            if not rel:
                skipped.append(f"{info.filename}（路径不安全）")
                continue
            if in_scope(rel, only):
                put(rel, zf.read(info))
    return files, commit, skipped


def export_subst(out, files):
    """.gitattributes 里标了 export-subst 的文件：整包下载时内容会被 git 替换，与仓库里的不同"""
    import fnmatch
    hit = set()
    for ga in [p for p in files if p == ".gitattributes" or p.endswith("/.gitattributes")]:
        base = ga[: -len(".gitattributes")]
        try:
            with open(os.path.join(out, *ga.split("/")), encoding="utf-8", errors="replace") as f:
                rules = [ln.split() for ln in f if "export-subst" in ln and not ln.lstrip().startswith("#")]
        except OSError:
            continue
        for r in rules:
            if not r or "-export-subst" in r[1:] or "export-subst" not in r[1:]:
                continue
            pat = r[0].lstrip("/")
            for p in files:
                if not p.startswith(base):
                    continue
                rel = p[len(base):]
                if fnmatch.fnmatch(rel if "/" in pat else rel.rsplit("/", 1)[-1], pat):
                    hit.add(p)
    return hit


def compare_tree(files, tree, only, sha, out=None):
    """与官方清单逐文件比对。返回 (是否通过, 缺失列表, 说明, 附注列表)"""
    want = {p: v for p, v in tree.items() if in_scope(p, only) and not v[2] == "160000"}
    subst = export_subst(out, files) if out else set()
    bad = [p for p, h in files.items() if p in want and want[p][0] != h and p not in subst]
    unsure = [p for p, h in files.items() if p in want and want[p][0] != h and p in subst]
    extra = [] if TRUNCATED[0] else [p for p in files if p not in want]
    missing = [p for p in want if p not in files]
    notes = []
    if unsure:
        notes.append(f"{len(unsure)} 个文件在 .gitattributes 里标了 export-subst，整包里的内容被替换过，未逐字核对（如 {unsure[0]}）")
    if TRUNCATED[0]:
        notes.append("GitHub 文件清单被截断，清单外的文件未核对")
    if bad:
        return False, missing, f"{len(bad)} 个文件与 GitHub 清单不符（如 {bad[0]}）", notes
    if extra:
        return False, missing, f"{len(extra)} 个文件不在 commit {sha[:12]} 的清单里（如 {extra[0]}）", notes
    return True, missing, "", notes


def via_tarball(url, sha, out, proxy, only, tree, label):
    log(f"· 方式：整包下载（{label}）")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        buf, got, last = tempfile.TemporaryFile(), 0, time.monotonic()
        with opener(proxy).open(req, timeout=60) as r:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                buf.write(chunk)
                got += len(chunk)
                if time.monotonic() - last > 10:
                    log(f"  已下载 {got / 1e6:.0f} MB")
                    last = time.monotonic()
        buf.seek(0)
        with buf:
            files, commit, skipped = extract_archive(buf, "tar", out, only)
    except Exception as e:
        log(f"  ✗ 整包下载失败：{type(e).__name__}: {e}")
        return None
    if commit and commit != sha:
        log(f"  ✗ 包里记录的 commit {commit[:12]} 与 {sha[:12]} 不一致")
        return None
    return files, skipped, commit


# ---------------------------------------------------------------- 方式三：逐文件（CDN / raw）
CDN_HOSTS = {"jsdelivr": ("cdn.jsdelivr.net", "/gh/{repo}@{sha}/{path}"),
             "raw": ("raw.githubusercontent.com", "/{repo}/{sha}/{path}")}


class Conn:
    """一个复用的 HTTPS 连接（可经 http 代理 CONNECT），断了自动重连"""

    def __init__(self, host, proxy):
        self.host, self.proxy, self.c = host, parse_proxy(proxy) if proxy else None, None

    def get(self, path):
        for attempt in range(3):
            try:
                if self.c is None:
                    if self.proxy:
                        self.c = http.client.HTTPSConnection(self.proxy[0], self.proxy[1], timeout=60,
                                                             context=ssl.create_default_context())
                        hdr = {"Proxy-Authorization": self.proxy[2]} if self.proxy[2] else None
                        self.c.set_tunnel(self.host, 443, headers=hdr)
                    else:
                        self.c = http.client.HTTPSConnection(self.host, timeout=60, context=ssl.create_default_context())
                self.c.request("GET", path, headers={"User-Agent": UA, "Connection": "keep-alive"})
                r = self.c.getresponse()
                body = r.read()
                return r.status, body
            except (OSError, http.client.HTTPException):
                try:
                    self.c.close()
                except Exception:
                    pass
                self.c = None
                time.sleep(1 + attempt * 2)
        return 0, b""


def via_cdn(repo, sha, out, proxy, only, tree, hosts, jobs, max_size):
    todo, skipped = [], []
    for p, (h, size, mode) in sorted(tree.items()):
        if not in_scope(p, only) or mode == "160000":
            continue
        if mode == "120000":
            skipped.append(f"{p}（符号链接）")
        elif max_size and size > max_size * 1e6:
            skipped.append(f"{p}（{size / 1e6:.1f} MB，超过 --max-size）")
        else:
            todo.append((p, h))
    log(f"· 方式：逐文件下载（{' → '.join(hosts)}，{jobs} 个复用连接），共 {len(todo)} 个文件")
    files, failed, lock = {}, [], threading.Lock()
    q = list(todo)
    for p, h in list(q):  # 断点续传：已存在且校验通过的不再下载
        dest = dest_path(out, p)
        if os.path.isfile(dest):
            with open(dest, "rb") as f:
                if blob_sha(f.read()) == h:
                    files[p] = h
                    q.remove((p, h))
    if files:
        log(f"  已有 {len(files)} 个文件校验通过，跳过")
    t0, done = time.monotonic(), [0]
    stats = {name: [0, 0] for name in hosts}  # 每个来源的 [成功, 失败]；某来源连续失败就不再用它

    def worker():
        conns = {name: Conn(CDN_HOSTS[name][0], proxy) for name in hosts}
        while True:
            with lock:
                if not q:
                    return
                p, h = q.pop(0)
            try:
                ok = fetch_one(conns, p, h)
            except Exception as e:  # 写文件失败（非法文件名、磁盘满等）也要记下来，不能悄悄丢掉
                ok = False
                with lock:
                    errors.append(f"{p}：{type(e).__name__}: {e}")
            with lock:
                if ok:
                    files[p] = h
                else:
                    failed.append(p)
                done[0] += 1
                if done[0] % 200 == 0:
                    log(f"  {done[0]}/{len(todo)}，{time.monotonic() - t0:.0f} 秒")

    def fetch_one(conns, p, h):
            ok = False
            for name in hosts:
                if stats[name][0] == 0 and stats[name][1] >= 20 and name != hosts[-1]:
                    continue  # 例如 jsDelivr 对超过 50 MB 的仓库一律拒绝
                host, tpl = CDN_HOSTS[name]
                st, body = conns[name].get(tpl.format(repo=repo, sha=sha, path=urllib.parse.quote(p)))
                good = st == 200 and blob_sha(body) == h
                with lock:
                    stats[name][0 if good else 1] += 1
                if good:
                    dest = dest_path(out, p)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "wb") as f:
                        f.write(body)
                    ok = True
                    break
            return ok

    errors = []
    ts = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, jobs))]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    failed += [p for p, _ in q]  # 理论上不会剩下；万一线程意外退出，剩下的也算失败
    for e in errors[:3]:
        log(f"  写文件失败：{e}")
    return files, skipped, failed


# ---------------------------------------------------------------- 主流程
def mirror_url(tpl, repo):
    if "{repo}" in tpl or "{url}" in tpl:
        return tpl.replace("{repo}", repo).replace("{url}", f"https://github.com/{repo}")
    return tpl.rstrip("/") + "/" + repo


def human(n):
    return f"{n / 1e6:.1f} MB" if n >= 1e5 else f"{n / 1e3:.0f} KB"


def recheck_skill_version(proxy, online=True):
    """开工时查不到本技能最新版本的（check_env.py 记过一笔），用这次走通的网络路线复查一次。
    这次没连上 github.com（用的压缩包或镜像）时不复查，留到下次"""
    if not online:
        return
    try:
        sys.dont_write_bytecode = True  # 不在技能目录里生成 __pycache__
        import version_check as vc
        line = vc.recheck_pending("" if proxy is None else proxy)
        if line:
            log(line)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="取固定 commit 的源码并校验（git clone 不可用或极慢时用）")
    ap.add_argument("repo", help="owner/repo")
    ap.add_argument("ref", help="40 位 commit，或 tag / 分支（会先解析成 commit）")
    ap.add_argument("out", help="输出目录，通常是 $OUT/src；必须不存在或为空（逐文件方式可续传）")
    ap.add_argument("--method", default="auto", choices=["auto", "git", "tarball", "cdn"])
    ap.add_argument("--only", action="append", default=[], help="只取这个目录（可重复）")
    ap.add_argument("--proxy", default="auto")
    ap.add_argument("--mirror", default=os.environ.get("RD_GITHUB_MIRROR", ""))
    ap.add_argument("--from-archive", help="用户提供的源码包（.zip / .tar.gz）")
    ap.add_argument("--host", default="jsdelivr,raw", help="逐文件下载的来源顺序，默认 jsdelivr,raw")
    ap.add_argument("--max-size", type=float, default=5.0)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--git-timeout", type=int, default=600)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    repo = re.sub(r"^https?://github\.com/", "", re.sub(r"\.git$", "", a.repo.strip())).strip("/")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        log(f"仓库写法不对：{a.repo}，应为 owner/repo")
        return 2
    only = [d.strip("/") for d in a.only if d.strip("/")]
    out = os.path.abspath(a.out)
    hosts = [h.strip() for h in a.host.split(",") if h.strip() in CDN_HOSTS] or ["jsdelivr", "raw"]
    notes = []

    proxy, probe, why = choose_route(a.proxy)
    if probe["ok"]:
        speed = "慢" if probe["secs"] > SLOW else "正常"
        log(f"· 网络：github.com 建连 {probe['secs']:.1f} 秒（{speed}），走{why}")
    elif probe["cert"] is False:
        log(f"· 网络：github.com 证书不受信（{probe['error']}）。常见原因是代理或安全软件在中间替换了证书；"
            "请把它的根证书导入系统或关掉 HTTPS 扫描。不要关闭证书校验。")
    else:
        log(f"· 网络：连不上 github.com（{probe['error']}）")
    slow = probe["ok"] and probe["secs"] > SLOW

    # 1. 解析 commit
    murl = mirror_url(a.mirror, repo) if a.mirror else None
    sha, sha_src = resolve_sha(repo, a.ref, proxy)
    if not sha and murl:
        sha, sha_src = resolve_sha(repo, a.ref, proxy, git_url=murl if murl.endswith(".git") else murl + ".git")
        if sha:
            notes.append("commit 号来自用户配置的镜像，未能与 GitHub 核对")
    if not sha:
        if a.from_archive:
            sha, sha_src = None, None
        else:
            log(f"✗ 解析不了 {a.ref} 对应的 commit：GitHub 和镜像都连不上。请传 40 位 commit 号，或改用 --from-archive")
            return 1
    if sha:
        log(f"· commit：{sha}" + ("" if sha_src == "given" else f"（由 {a.ref} 解析）"))

    tree = get_tree(repo, sha, proxy) if sha else None
    if tree is not None:
        scope = {p: v for p, v in tree.items() if in_scope(p, only)}
        log(f"· 规模：{len(scope)} 个文件，合计 {human(sum(v[1] for v in scope.values()))}"
            + (f"（只算 {', '.join(only)}）" if only else ""))
    if a.dry_run:
        if tree is None:
            log("拿不到文件清单，无法估算规模")
            return 1
        big = [p for p, v in scope.items() if v[1] > a.max_size * 1e6] if a.max_size else []
        log(f"· 逐文件下载会跳过 {len(big)} 个大于 {a.max_size:g} MB 的文件")
        return 0

    # 输出目录
    if os.path.exists(out) and (not os.path.isdir(out) or os.listdir(out)):
        partial = os.path.isfile(os.path.join(out, ".rd-partial"))
        if not (partial and a.method in ("auto", "cdn")):
            log(f"✗ 输出目录 {out} 已存在且不为空；换个目录，或确认可以删除后再运行")
            return 2
    created = not os.path.exists(out)
    partial_flag = os.path.join(out, ".rd-partial")
    tmp = f"{out}.rd-tmp-{os.getpid()}"  # git 和整包先放临时目录，成功才换上，失败不碰输出目录

    def fresh_tmp():
        if os.path.exists(tmp):
            shutil.rmtree(tmp)
        os.makedirs(tmp)
        return tmp

    def drop_tmp():
        if os.path.exists(tmp):
            shutil.rmtree(tmp, ignore_errors=True)

    def install():
        """把临时目录换成输出目录：输出目录只可能是空的，或是本脚本上次没下完的（有 .rd-partial）"""
        if os.path.isdir(out):
            if os.path.isfile(partial_flag):
                shutil.rmtree(out)
            elif not os.listdir(out):
                os.rmdir(out)
            else:
                raise RuntimeError(f"输出目录 {out} 不为空")
        os.rename(tmp, out)

    def finish(source, files, verified, skipped, extra_notes=()):
        write_manifest(out, repo, sha, source, files, verified, skipped, notes + list(extra_notes))
        if os.path.exists(partial_flag):
            os.remove(partial_flag)
        log(f"✓ 完成：{len(files)} 个文件" + (f"，跳过 {len(skipped)} 个（见 .rd-manifest.json）" if skipped else "")
            + ("，已逐文件对照 GitHub 清单" if verified else "，未能对照 GitHub 清单"))
        log("· 注意：这不是 git 仓库，没有提交历史——热点文件、git blame、提交统计做不了；社区数据改用 GitHub API")
        recheck_skill_version(proxy, probe["ok"])
        log(f"取码方式: {source}；commit {sha}；" + ("已校验" if verified else "未校验") + (f"；只取 {', '.join(only)}" if only else ""))
        return 0

    # 0. 用户提供的压缩包
    if a.from_archive:
        if not os.path.isfile(a.from_archive):
            log(f"✗ 找不到压缩包 {a.from_archive}")
            return 2
        try:
            kind = "zip" if zipfile.is_zipfile(a.from_archive) else "tar"
            with open(a.from_archive, "rb") as f:
                files, commit, skipped = extract_archive(f, kind, fresh_tmp(), only)
        except Exception as e:
            drop_tmp()
            log(f"✗ 解不开压缩包 {a.from_archive}（{type(e).__name__}: {e}）；支持 .zip、.tar.gz")
            return 2
        if sha and commit and commit != sha:
            drop_tmp()
            log(f"✗ 压缩包记录的 commit {commit[:12]} 与 {sha[:12]} 不一致")
            return 1
        if not sha and commit:
            sha = commit
            tree = get_tree(repo, sha, proxy)
        if not sha:
            notes.append("压缩包没有记录 commit，命令里也没给 40 位 commit，版本未核对")
            sha = "unknown"
        elif not commit and sha_src == "given":
            notes.append("commit 由命令参数给出，压缩包里没有记录")
        verified, extra = False, []
        if tree is not None:
            verified, missing, err, extra = compare_tree(files, tree, only, sha, tmp)
            if err:
                drop_tmp()
                log(f"✗ 压缩包与 GitHub 清单不符：{err}")
                return 1
            if missing:
                skipped += [f"{p}（压缩包里没有）" for p in missing]
        install()
        return finish(f"用户提供的压缩包 {os.path.basename(a.from_archive)}", files, verified, skipped, extra)

    order = ["git", "tarball", "cdn"] if a.method == "auto" else [a.method]
    resuming = os.path.isfile(os.path.join(out, ".rd-partial"))
    if a.method == "auto" and (slow or not probe["ok"]):
        order = ["tarball", "cdn", "git"]  # 建连很慢时先用单连接整包，git 放最后
    if only and a.method == "auto":
        order = [m for m in order if m != "git"] + ["git"]  # 只取部分目录时整包/逐文件更省
    if resuming and a.method == "auto":
        order = ["cdn"] + [m for m in order if m != "cdn"]  # 上次逐文件下载没完成，先续传
    have_git = bool(shutil.which("git"))

    for m in order:
        if m == "git" and have_git:
            for url, label in ([(murl, "用户配置的镜像")] if murl else []) + ([(f"https://github.com/{repo}.git", why)] if probe["ok"] else []):
                if not sha or not re.fullmatch(r"[0-9a-f]{40}", sha):
                    break
                fresh_tmp()  # git clone 可以克隆进空目录
                if via_git(url, sha, tmp, proxy, a.git_timeout, label):
                    install()
                    log("✓ 完成：git 仓库（含历史）")
                    recheck_skill_version(proxy, probe["ok"])
                    log(f"取码方式: git clone（{label}）；commit {sha}；git 已按 commit 校验对象")
                    return 0
                drop_tmp()
        elif m == "tarball":
            srcs = []
            if probe["ok"]:
                srcs.append((f"https://codeload.github.com/{repo}/tar.gz/{sha}", f"codeload.github.com，{why}"))
            if murl:
                srcs.append((re.sub(r"\.git$", "", murl) + f"/archive/{sha}.tar.gz", "用户配置的镜像"))
            for url, label in srcs:
                r = via_tarball(url, sha, fresh_tmp(), proxy, only, tree, label)
                if not r:
                    drop_tmp()
                    continue
                files, skipped, commit = r
                verified, extra = False, []
                if tree is not None:
                    verified, missing, err, extra = compare_tree(files, tree, only, sha, tmp)
                    if err:
                        drop_tmp()
                        log(f"  ✗ 校验不通过：{err}")
                        continue
                    skipped += [f"{p}（.gitattributes 设为 export-ignore，整包里没有）" for p in missing]
                elif not commit:
                    drop_tmp()
                    log("  ✗ 既拿不到 GitHub 清单，包里也没记录 commit，无法确认版本")
                    continue
                else:
                    extra = ["没拿到 GitHub 文件清单，只核对了包里记录的 commit" + ("（commit 记录由镜像提供）" if "镜像" in label else "")]
                install()
                return finish(f"整包下载（{label}）", files, verified, skipped, extra)
        elif m == "cdn":
            if tree is None:
                log("· 逐文件下载需要 GitHub 文件清单（api.github.com），拿不到，跳过")
                continue
            os.makedirs(out, exist_ok=True)
            open(partial_flag, "w").close()
            files, skipped, failed = via_cdn(repo, sha, out, proxy, only, tree, hosts, a.jobs, a.max_size)
            extra = ["GitHub 文件清单被截断，只下载了清单内的文件"] if TRUNCATED[0] else []
            if failed:
                log(f"  ✗ {len(failed)} 个文件下载失败（如 {failed[0]}）；重新运行同一命令会续传")
                if len(failed) <= max(20, len(files) // 50):
                    skipped += [f"{p}（下载失败）" for p in failed]
                    return finish(f"逐文件下载（{' / '.join(hosts)}）", files, True, skipped,
                                  extra + [f"{len(failed)} 个文件下载失败，未纳入分析"])
                continue
            return finish(f"逐文件下载（{' / '.join(hosts)}）", files, True, skipped, extra)

    drop_tmp()
    if created and os.path.isdir(out) and not os.path.isfile(partial_flag):
        shutil.rmtree(out, ignore_errors=True)
    log("✗ 所有方式都失败了。可以：")
    log("  1. 打开本机代理（如 Clash）后重试，脚本会自动发现常见端口；或用 --proxy http://127.0.0.1:<端口>")
    log("  2. 如果你有可信的 GitHub 镜像，设置 RD_GITHUB_MIRROR 后重试（脚本会按固定 commit 校验）")
    log("  3. 看看项目在 Gitee / GitCode 上有没有官方镜像，或在浏览器里下载源码 ZIP，用 --from-archive 传入")
    log("  4. 直接提供本地仓库路径")
    return 1


if __name__ == "__main__":
    sys.exit(main())
