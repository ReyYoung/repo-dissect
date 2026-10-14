# 运行与截图：细则

SKILL.md 第 3 节的补充。脚本是 `scripts/run_project.py`，只用 Python 标准库；截图需要 Python `playwright`（没有就跳过截图，其余照常）。

## 1. 命令一览

| 命令 | 作用 | 会改动什么 |
|---|---|---|
| `plan <OUT>` | 只读检查环境和项目，生成决策卡片 `run/plan.md`、`run/plan.json`；没有 `run/pages.json` 时生成截图页面初稿 | 只写 `$OUT/run/` |
| `prepare <OUT>` | 建项目副本 `run/work` 并生成 `.env`（可选：所在环境有文件授权弹窗时，先在前台执行它） | 只写 `$OUT/run/work` |
| `run <OUT>` | 建副本（已 `prepare` 过则复用）→ 启动 Docker（需要时）→ 拉镜像 → 启动 → 等就绪 → 截图 → 清理 | 用户已在卡片上同意的那些 |
| `screenshot <OUT>` | 对正在运行的项目按 `pages.json` 截图 | 只写 `$OUT/img/screens/` |
| `cleanup <OUT>` | 停止并删除本次的容器、网络、新建的数据卷和项目副本 | 只动项目名 `rd-<仓库名>-<编号>` 下的资源 |
| `handoff <OUT>` | 生成交给用户电脑上 Agent 的接力指令 `run-locally.md` | 只写 `$OUT/` |

常用参数：
- `plan --src <路径>`（本地仓库，代码不在 `$OUT/src` 时）、`--compose <文件>`（仓库有多个 compose 文件时指定，例如 Mac 专用的 `docker-compose-macos.yml`；卡片"注意"里会列出其他候选）、`--min-mem 16` 等（文档没写最低配置时手动指定）；
- `run --timeout-min 25`、`--keep`、`--pages <文件>`（默认 `$OUT/run/pages.json`）、`--login 账号:密码`（也可用环境变量 `RD_LOGIN`）、`--base <地址>`（脚本识别不出网页地址时指定）。

## 2. 卡片长什么样

`plan` 的输出就是卡片，原样给用户即可，不用改写。可运行时示例（数字为示意）：

```text
## 运行决策：要把 demo-app 跑起来截图吗？

**结论：可以在这台机器上运行**（预计 20 分钟）
- 注意：1 个服务只有 x86 镜像（worker），会按 x86 转译运行，速度较慢

| 项目 | 情况 |
|---|---|
| Docker | 未运行，可自动启动（OrbStack） |
| 镜像 | 5 个：需下载 5 个，约 4.2 GB |
| 本机资源 | 10 核 / 24 GB 内存 / 可用磁盘 180 GB；项目要求：CPU ≥ 4 核、内存 ≥ 16 GB、磁盘 ≥ 50 GB |
| 占用端口 | 80、443、9380 |
| 访问地址 | http://localhost |

**请选择：**
1. 在这台机器上运行并截图（推荐）……
2. 只做静态分析，跳过运行

选 1 时会对系统做的改动：启动 OrbStack；把 Docker 虚拟机的内核参数 vm.max_map_count 调到 262144……
```

卡片里的选项已经按情况写好，照着给用户即可：

| 结论（退出码） | 给用户的选项 | 用户选了之后 |
|---|---|---|
| 可以运行（0） | 本机运行 / 只做静态分析 | `run` |
| 需先处理（2） | 我处理好了，开始运行 / 只做静态分析 | 用户处理完后重新 `plan`，结论为 0 就直接 `run` |
| 跑不了，推荐交接（3，`plan.json` 里 `recommend` 为 `handoff`：云端、沙箱、访问不了镜像仓库） | 交给我电脑上的 Agent / 只做静态分析 | `handoff`，把接力指令和结果目录交给用户 |
| 跑不了，问题在本机（3，`recommend` 为 `recheck`：没装 Docker、磁盘或内存不够） | 我处理好了，重新检查 / 交给另一台电脑 / 只做静态分析 | 重新 `plan`，或 `handoff` |
| 跑不了，问题在项目本身（3，`recommend` 为 `static`：没有 compose 文件、没有本机架构的镜像、compose 里只有基础设施） | 只做静态分析 | 需要时按项目文档在容器里手动启动，遵守同样的安全边界 |

**选的 compose 文件不对**：`plan` 会在根目录和部署目录里找（最多 6 层，路径带 dev、test、template 的排后面），找到好几份时按目录和文件名选一份，并在卡片里列出其他候选。项目文档（README、部署文档）指定了别的文件，或按数据库、地区分了好几份时，读文档后用 `plan "$OUT" --compose <路径>` 重新检查。

**只有基础设施的 compose**：很多项目的 `docker-compose.yml` 只启动数据库、缓存、消息队列、对象存储（postgres、redis、clickhouse、kafka / redpanda、minio、elasticsearch 等），应用本身要在本机装依赖（如 `bun install`、`pnpm install`，常常是 GB 级）后另行启动。这时卡片结论是"只有基础设施能启动，应用本身跑不起来，无法截图"（`plan.json` 里 `infra_only: true`），**不要对用户说"可以运行"**。仓库里另有包含应用服务的 compose 文件时，用 `--compose <路径>` 指定后重新 `plan`。

检查本身出错时（例如 Agent 的文件沙箱拦截了某个操作），`plan` 也会写出一张卡片：结论"当前环境没能完成运行检查"、原因的白话说明、推荐交接，退出码 3。照常给用户选。

卡片出现"⚠ 这个项目要求较高的主机权限"（特权模式、挂载 docker.sock 或项目以外的本机目录、主机网络等）时，第一个选项会变成"我了解上述权限，在这台机器上运行"，不再标推荐。

用环境的选项式提问工具时，选项文字用上表第二列，卡片正文放在问题说明里；没有这类工具就在回复里贴卡片、列编号选项。

## 3. pages.json

`plan` 会按前端路由生成一份初稿（Next.js 的 `app/`、`pages/` 目录，React Router / Vue Router 配置里的 `path`，包括 `Routes.Datasets` 这类常量写法；跳过动态路由和登录、安装类页面）。L1 完成后按功能清单修订成 5–10 个能证明主要功能的页面，名字用"序号-页面名"，会成为截图文件名：

```json
[
  {"name": "00-首页", "path": "/"},
  {"name": "01-知识库列表", "path": "/knowledge"},
  {"name": "02-对话", "path": "/chat", "wait_ms": 3000}
]
```

- `path` 可以是相对地址，也可以是完整 URL；`wait_ms` 是页面加载后再等多久（默认 1500 毫秒，图表多的页面调大）。
- 初稿没覆盖的页面，从前端路由定义里找（如 `web/src/routes.ts`、`router/index.ts`、Next.js 的 `app/` 或 `pages/` 目录），不要猜；带参数的详情页（`/datasets/[id]`）要先在列表页里拿到真实 id 再写。
- 每张截图旁有同名 `.txt`，是页面上的文字；看不了图片时据此判断功能是否存在。

## 4. 登录

- 有默认管理员账号（项目文档或 `.env` 里写明的本地初始账号）：直接 `run --login 账号:密码`。
- 需要先注册：`run --keep` → 用浏览器自动化在注册页注册一个明显虚构的账号（`admin@example.com`、随机生成的密码，不用用户的真实信息）→ `screenshot <OUT> --login 账号:密码` → `cleanup <OUT>`。
- 脚本登录后如果还停在登录页，会在 `run.log` 里提示；这时用浏览器自动化手动登录后再截。
- 截图里带 `warning`（页面 4xx/5xx、显示登录框）的不能当证据。

## 5. 失败了怎么办

`result.json` 的 `reason` 是卡在哪，`advice` 是给用户的一句白话建议，`detail` 是关键报错原文；服务启动后退出时，日志存在 `run/logs-<服务名>.txt`。脚本能识别的常见原因：

| 现象 | 给用户的建议 |
|---|---|
| 容器被杀（137、OOM） | 在 OrbStack / Docker Desktop 里调大内存上限，或关闭其他占内存的程序 |
| Elasticsearch 报 `vm.max_map_count` | 重新运行一次（Docker 重启过会恢复默认值） |
| 端口被占用 | 关掉占用端口的程序，或改项目 `.env` 里的端口 |
| 磁盘不足 | 清理磁盘，或用 `docker rmi` 删除不再需要的镜像 |
| 没有本机架构的镜像 | 脚本会自动改为按 x86 转译运行；仍失败说明转译不可用 |
| 镜像不存在或需要登录 | 检查项目 `.env` 里的镜像名和版本 |
| Docker Hub 匿名下载次数用完 | 过一小时再试，或登录 Docker Hub、配置镜像加速 |
| 已有同名容器 | 先停止并删除那个容器（多半是用户之前部署的同一个项目，要用户确认） |
| 网络不通或太慢 | 检查网络、代理或镜像加速设置（见下方"镜像仓库连不上"） |
| 容器里找不到要执行的程序 | 镜像版本和 compose 文件不匹配，检查 `.env` 里的镜像版本 |

处理原则：把 `advice` 转告用户；属于用户电脑设置的事（内存上限、关闭其他程序）由用户做，做完说一声再试一次；同一问题最多重试一次，然后转静态分析，在 `index.md` 写明卡在哪。

## 6. 交给用户电脑上的 Agent

云端、禁网沙箱、没有 Docker 的机器上，`plan` 会给出"本环境跑不了"。这时 `handoff` 生成 `run-locally.md`，里面有一句可直接转发的指令，例如：

```text
用 repo-dissect 技能为 https://github.com/infiniflow/ragflow 的 commit <sha> 补做第 3 节「运行与截图」，输出目录 ~/repo-dissect/ragflow/：先运行 run_project.py plan 给我一张运行决策卡片，我选定后由你完成运行、截图、回填功能清单并重新生成 report.html。
```

收到这句话的 Agent：结果目录已在本地就在原结果上补；没有就先克隆到 `<输出目录>/src` 并固定到给定 commit、写好 `_vars.sh`，然后从 `plan` 开始，同样只问用户一次。`run/pages.json` 已随结果目录带过去时直接使用。

## 7. 带文件沙箱的 Agent

有的 Agent（如 WorkBuddy）给文件操作加了沙箱：对已存在的目录建目录会报错，`.env` 类文件当作凭证要人工授权，后台任务拿不到授权。脚本的处理：

- 建目录都做了兼容，重复执行 `plan`、`handoff` 不会因目录已存在而失败；
- `plan` 只读，不复制项目、不生成 `.env`（解析 compose 时直接引用项目自带的 `.env.example`），几秒完成，适合前台执行；
- 复制副本、生成 `.env` 集中在 `prepare`（`run` 开头也会做）：先在前台执行 `prepare` 完成授权，再把 `run` 放到后台；`.env` 生成失败只记一条日志，不中断；
- `check_env.py` 的"文件沙箱"一行会提前探测这两类限制。

## 8. 镜像仓库连不上

脚本让 Docker 守护进程自己去查镜像清单来判断仓库能否访问（守护进程的网络和代理可能和 Agent 进程不同），所以卡片上的"访问不了镜像仓库"指的是 Docker 真的拉不下来。常见原因和处理：

- **Mac + OrbStack + 代理软件（如 Clash）**：OrbStack 启动时读取系统代理；代理软件晚于 OrbStack 打开，Docker 就不走代理。先开代理再重启 OrbStack，或固定代理：`orb config set network_proxy socks5://127.0.0.1:<端口>`（改回跟随系统：`orb config set network_proxy auto`）。代理规则需让 `registry-1.docker.io`、`auth.docker.io`、`production.cloudflare.docker.com` 以及项目用到的其他仓库（`ghcr.io`、`quay.io` 等）走代理。
- **Docker Desktop**：Settings → Resources → Proxies 填代理地址，或在 Docker Engine 配置里加 `registry-mirrors`。
- **没有代理**：给 Docker 配镜像加速（`registry-mirrors` 只对 Docker Hub 生效，`ghcr.io`、`quay.io` 等仍需代理）。
- **云端 / 沙箱环境**：出站网络由平台的白名单控制，通常拉不了镜像；直接交给用户电脑上的 Agent。
