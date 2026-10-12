# RAGFlow v0.27.2 选型证据：License / 安全 / 信创 / 离线部署

- 仓库：infiniflow/ragflow，tag `v0.27.2`，commit `a024bea0cd93f39e6652a42bf84dd20c55bc560b`（已用 `git rev-parse HEAD` 核对）
- 场景：私有化交付给央国企客户；约束是信创国产化和内网离线部署
- 标记：✅ 代码事实（有行号出处）｜🔍 推断（依据经验或外部常识，需复核）｜❓ 未确认
- 永久链接前缀：`https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/`
- 口令与密钥只写位置，不写值

---

## 1. License

### 1.1 根 LICENSE
- ✅ 根 LICENSE 共 201 行。与 Debian 自带的标准文本 `/usr/share/common-licenses/Apache-2.0` 做 diff，结果只差文件开头一个空行，**没有附加条款或 Commons Clause 一类的限制**。见 [LICENSE:L1-L201](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/LICENSE#L1-L201)。条款在 [LICENSE:L176](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/LICENSE#L176) 结束，之后是标准 APPENDIX。
- ✅ `pyproject.toml` 声明 `license-files = ["LICENSE"]`，见 [pyproject.toml:L6](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L6)。
- ✅ `git ls-files | grep -iE 'licen[cs]e|copying|notice'` 只命中 `LICENSE`、`internal/admin/license_ee.go`、`internal/dao/license.go`、`internal/entity/license.go`。**没有 NOTICE 文件**，也没有第三方 LICENSE 汇总（THIRD-PARTY）。
- 🔍 Apache-2.0 第 4 条要求再分发时保留版权声明，若上游有 NOTICE 也要保留。上游没有 NOTICE，但镜像里打包了大量第三方组件（见 1.3），交付方需要自己整理一份第三方声明。

### 1.2 "企业版"占位文件（`*_ee.go`）
这些文件全部带 Apache-2.0 文件头，例如 [internal/admin/license_ee.go:L1-L8](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/admin/license_ee.go#L1-L8)。内容是空实现或返回"not supported"的桩，说明**存在一个闭源企业版，用同名文件替换这些桩**。

| 能力 | 开源版行为 | 出处 |
|---|---|---|
| 版本类型 | 固定返回 `open source` | ✅ [internal/common/version_ee.go:L18-L22](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/common/version_ee.go#L18-L22) |
| License 校验 | `InitLicense` 直接返回 nil；`CheckLicense` 恒返回有效 | ✅ [internal/admin/license_ee.go:L19-L20](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/admin/license_ee.go#L19-L20)、[internal/admin/service_ee.go:L1204-L1205](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/admin/service_ee.go#L1204-L1205) |
| 设置、查看 License 和机器指纹 | 不支持 | ✅ [internal/admin/service_ee.go:L363-L419](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/admin/service_ee.go#L363-L419) |
| 角色、权限（RBAC）：建角色、授权、改用户角色 | Go 侧全部返回 not supported | ✅ [internal/admin/service_ee.go:L37-L179](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/admin/service_ee.go#L37-L179) |
| 角色、权限（Python admin 默认路径） | 抛出 `not implement` 异常 | ✅ [admin/server/roles.py:L25-L28](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/admin/server/roles.py#L25-L28) |
| 模型供应商的集中管理、用户用量、配额、存储报表、数据清理、管理员代建 API key | not supported | ✅ [internal/admin/service_ee.go:L188-L1191](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/admin/service_ee.go#L188-L1191) |
| **敏感词上传、下载** | not supported | ✅ [internal/admin/service_ee.go:L1208-L1225](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/admin/service_ee.go#L1208-L1225) |
| **操作审计日志落库（写 ClickHouse）** | `SaveOperationLog` 是空实现，直接返回 nil | ✅ [internal/engine/clickhouse/clickhouse_ee.go:L44](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/engine/clickhouse/clickhouse_ee.go#L44) |
| OAuth、GitHub、飞书、**ICBC（工行）**、Azure 登录，验证码，OTP（Go 侧） | 路由已注册，但处理函数返回 NotImplemented | ✅ [internal/router/router_ee.go:L26-L36](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/router/router_ee.go#L26-L36)、[internal/handler/user_auth_ee.go:L25-L26](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/handler/user_auth_ee.go#L25-L26) |
| 计费、OAuth 配置 | 空实现 | ✅ [internal/server/config/billing_ee.go:L24-L25](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/server/config/billing_ee.go#L24-L25) |
| 前端企业功能开关 | 由构建变量 `VITE_RAGFLOW_ENTERPRISE` 控制 | ✅ [web/src/pages/admin/utils.tsx:L79-L80](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/web/src/pages/admin/utils.tsx#L79-L80)、[enterprise-feature.tsx:L8](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/web/src/pages/admin/components/enterprise-feature.tsx#L8) |

- ✅ 官方 FAQ 明确说企业版的 DeepDoc 模型"用专有数据预训练"，并且有"更完善的团队权限控制"，见 [docs/faq.mdx:L73](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docs/faq.mdx#L73)。**开源版的解析模型和企业版不同。**
- ✅ 企业版另有按角色设置默认模型的功能，见 [docs/administrator/configurations/configurations.md:L259](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docs/administrator/configurations/configurations.md#L259)。
- 🔍 结论：开源版缺少细粒度 RBAC、审计日志、敏感词过滤、配额管控和企业 SSO 通道。这几项正是央国企等保和内控常问的。要么二次开发补齐，要么采购企业版。
- 补充：`*_ee.go` 主要作用于 Go 服务路径。`.env` 默认 `API_PROXY_SCHEME=python`，见 [docker/.env:L251](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L251)。但 Python admin 的角色功能同样是桩（见上表），结论不变。

### 1.3 前端 Logo 与版权
- ✅ Logo 是硬编码的 `/logo.svg`，见 [web/src/layouts/components/header.tsx:L83](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/web/src/layouts/components/header.tsx#L83) 和 [global-navbar.tsx:L270](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/web/src/layouts/components/global-navbar.tsx#L270)。"Powered by RAGFlow"只是嵌入对话框的占位文本，见 [web/src/components/embed-dialog/index.tsx:L463](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/web/src/components/embed-dialog/index.tsx#L463)。没有找到强制展示版权的逻辑。
- 🔍 Apache-2.0 没有强制署名展示的要求，可以换 Logo 做白标。但第 6 条不授予商标权：对外产品不能以"RAGFlow"商标的名义销售。

### 1.4 依赖协议
**说明**：`uv.lock` 没有 license 字段（✅ `grep -n license uv.lock` 无结果），Python 和 Go 依赖的协议均靠经验判断（🔍）。`web/package-lock.json` 自带 `license` 字段，结论为 ✅。

#### Python（`uv.lock` 共 697 个包；依赖链由本地脚本解析 `uv.lock` 得出）
| 包（锁定版本） | 引入方式 | 协议（🔍） | 链接方式 | 出处 |
|---|---|---|---|---|
| **extract-msg 0.55.0** | 直接依赖 | **GPL-3.0** | 在进程内 import | ✅ [pyproject.toml:L43](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L43)；import 位置 [rag/flow/parser/parser.py:L1332](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/rag/flow/parser/parser.py#L1332) |
| ├ pcodedmp（经 oletools → rtfde → extract-msg 引入） | 传递依赖 | GPL-3.0 | 进程内 | uv.lock 依赖链 |
| ├ rtfde | 传递依赖 | LGPL-3.0 | 进程内 | 同上 |
| mysql-connector-python 9.3.0 | 直接依赖 | GPL-2.0 + Universal FOSS Exception | 进程内（仅用于 RDBMS 数据源连接器） | ✅ [pyproject.toml:L73](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L73)、[common/data_source/rdbms_connector.py:L174](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/common/data_source/rdbms_connector.py#L174) |
| demjson3 3.0.6 | 直接依赖 | LGPL-3.0 | 进程内 | ✅ [pyproject.toml:L35](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L35)、[deepdoc/parser/resume/step_two.py:L22](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/deepdoc/parser/resume/step_two.py#L22) |
| chardet 5.2.0 | 直接依赖 | LGPL-2.1 | 进程内 | ✅ [pyproject.toml:L28](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L28)、[rag/nlp/__init__.py:L24](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/rag/nlp/__init__.py#L24) |
| paramiko 5.0.0 | 直接依赖 | LGPL-2.1 | 进程内（SSH 沙箱 provider） | ✅ [pyproject.toml:L97](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L97)、[agent/sandbox/providers/ssh.py:L45](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/agent/sandbox/providers/ssh.py#L45) |
| psycopg2-binary 2.9.11 | 直接依赖 | LGPL-3.0（含例外） | 进程内（PostgreSQL / GaussDB 元数据库） | ✅ [pyproject.toml:L87](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L87) |
| python-telegram-bot 22.7 | 直接依赖 | LGPL-3.0 | 进程内 | ✅ [pyproject.toml:L191](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L191) |
| gensim（经 graspologic 引入） | 传递依赖 | LGPL-2.1 | 进程内 | ✅ graspologic 来自 gitee 的 git 依赖，见 [pyproject.toml:L56](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L56) |
| datrie、hanziconv（经 infinity-sdk 引入） | 传递依赖 | datrie 为 LGPL-2.1；hanziconv 需复核 | 进程内（中文分词） | ✅ [pyproject.toml:L60](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L60) |
| frozendict（经 yfinance 引入） | 传递依赖 | LGPL-3.0 | 进程内 | — |
| pydivert（经 selenium-wire 引入，仅 Windows） | 传递依赖 | LGPL-3 / GPL-2 二选一 | 不适用于 Linux | — |
| spaCy 模型 es / fr / pt / ja | 直接依赖（GitHub wheel） | es 为 GPL-3.0；fr 为 LGPL-LR；pt、ja 为 CC BY-SA 4.0 | 数据和模型 | ✅ [pyproject.toml:L120-L126](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L120-L126) |
| crawl4ai 0.9.2 | 直接依赖 | Apache-2.0，**可能带署名要求**（需复核） | 进程内 | ✅ [pyproject.toml:L31](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L31) |
| text-unidecode | 传递依赖 | Artistic / GPL 二选一 | 进程内 | — |
| certifi、tqdm | 传递依赖 | MPL-2.0（文件级弱 copyleft） | — | — |
| opencv-python 与 opencv-python-headless 4.10 | 直接依赖，两者同时声明 | Apache-2.0；wheel 内捆绑 FFmpeg（LGPL）和 Qt（LGPL） | 进程内 | ✅ [pyproject.toml:L80-L81](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L80-L81) |

- ✅ **没有 PyMuPDF / fitz（AGPL）**：在 `uv.lock` 中检索 `mupdf|fitz|pymupdf` 无结果。PDF 解析用的是 pdfplumber 0.11.10 + pdfminer.six + pypdf + pypdfium2（🔍 依次为 MIT、MIT、BSD、Apache/BSD）。
- ✅ tika 只是 Python 客户端，在 [pyproject.toml:L134](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L134)。Tika Server 是 jar，以独立 Java 进程运行（🔍 Apache-2.0）。
- 🔍 结论：Python 进程内**最强的传染性依赖是 extract-msg（GPL-3.0，用于解析 Outlook .msg 文件）**。它在 Python 中按 import 使用，GPL 对 Python import 是否构成"链接"一直有争议；保守做法是视为整体分发受 GPL 约束。对策是删掉该依赖、禁用 .msg 解析，或把它拆成独立进程服务。其余主要是 LGPL：Python 动态 import 一般可接受，条件是保留许可证文本并允许用户替换该库。

#### 镜像内的系统组件（以独立程序方式调用）
- ✅ Dockerfile 通过 apt 安装 `ghostscript`（🔍 AGPL-3.0）、`pandoc`（🔍 GPL-2.0+）和 texlive，见 [Dockerfile:L54](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/Dockerfile#L54)。ghostscript 由 subprocess 调用 `gs` 修复 PDF，见 [api/utils/file_utils.py:L156-L171](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/api/utils/file_utils.py#L156-L171)。pandoc 由 pypandoc 调用，见 [agent/component/docs_generator.py:L234](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/agent/component/docs_generator.py#L234)。
  - 🔍 这属于独立进程调用，**不构成衍生作品**。但**再分发镜像就等于分发 AGPL/GPL 二进制**，需要提供对应源码或获取方式（GPL 第 6 条 / AGPL 第 6 条）。
- ✅ **Microsoft ODBC Driver（msodbcsql17/18，专有 EULA，安装时 `ACCEPT_EULA=Y`）**，见 [Dockerfile:L162-L165](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/Dockerfile#L162-L165)。🔍 专有软件随镜像二次分发，需要核对微软的再分发条款。
- ✅ Chrome for Testing 121 和 chromedriver，见 [Dockerfile:L172-L179](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/Dockerfile#L172-L179)。🔍 Google 的分发条款需要复核。

#### Go（[go.mod](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/go.mod)）
- 🔍 主依赖 gin、go-elasticsearch、minio-go、go-redis、golang-jwt、nats-server、excelize、gonja 等都是 MIT、BSD 或 Apache。没有发现 GPL 类依赖。
- 需要复核的：
  - **静态链接**进 Go 二进制的原生库：`pdf_oxide`、`office_oxide`、`pdfium-static`、`onnxruntime`，见 [go.mod:L62-L63](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/go.mod#L62-L63) 和 [ragflow_deps/download_deps.py:L85-L101](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/ragflow_deps/download_deps.py#L85-L101)。
  - 被 replace 到个人仓库的 `gomsg`，见 [go.mod:L181](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/go.mod#L181)。
  - `gojianfan`，见 [go.mod:L58](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/go.mod#L58)。

#### 前端（`web/package-lock.json` 自带 license 字段，共 2047 个条目）✅
- 协议分布：MIT 1766、ISC 119、BSD-3 49、Apache-2.0 43，其余为少量宽松协议。**没有 GPL、AGPL 或 SSPL 独占协议的包**。
- 唯一含 GPL 的是 jszip `(MIT OR GPL-3.0-or-later)`，可以选 MIT，见 [web/package-lock.json:L17855](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/web/package-lock.json#L17855)。dompurify 为 `(MPL-2.0 OR Apache-2.0)`。
- format、khroma、rc-tween-one 三个包没有 license 字段，需要人工复核。
- ✅ xlsx 锁定在 0.18.5（Apache-2.0），且 resolved 地址是 npmmirror，见 [web/package-lock.json:L28353-L28357](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/web/package-lock.json#L28353-L28357)。🔍 该版本有已知 CVE（原型污染、ReDoS）。

#### 中间件镜像（全部以独立服务方式通过网络调用）
| 组件 | 镜像 | 协议（🔍） | 出处 |
|---|---|---|---|
| Elasticsearch（**默认文档引擎**） | `elasticsearch:${STACK_VERSION}`，默认 8.11.3 | **8.11 只能在 SSPL 和 ELv2 中二选一**；AGPL 选项从 8.16 起才有 | ✅ [docker-compose-base.yml:L5](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L5)、[docker/.env:L41](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L41) |
| Kibana（可选） | `kibana:${STACK_VERSION}` | SSPL / ELv2 | ✅ [docker-compose-base.yml:L360](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L360) |
| 对象存储 | `pgsty/silo:RELEASE.2026-08-06…`（**不是 MinIO 官方镜像**，是 Pigsty 维护的 MinIO 分支） | 🔍 MinIO 衍生品，应为 AGPL-3.0 | ✅ [docker-compose-base.yml:L249](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L249)；换镜像原因见 [docs/release_notes.md:L482](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docs/release_notes.md#L482) |
| MySQL | `mysql:8.0.40` | GPL-2.0（社区版） | ✅ [docker-compose-base.yml:L222](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L222) |
| Redis | `valkey/valkey:8` | BSD-3 | ✅ [docker-compose-base.yml:L271](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L271) |
| Infinity | `infiniflow/infinity:v0.7.3-x64-v3` | Apache-2.0 | ✅ [docker-compose-base.yml:L79](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L79) |
| OpenSearch | `opensearchproject/opensearch:2.19.1` | Apache-2.0 | ✅ [docker-compose-base.yml:L43](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L43) |
| OceanBase CE | `oceanbase/oceanbase-ce:4.4.1.0` | 木兰公共许可证 MulanPubL-2.0 | ✅ [docker-compose-base.yml:L127](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L127) |
| SeekDB | `oceanbase/seekdb:latest`（**未锁定版本**） | 待复核 | ✅ [docker-compose-base.yml:L158](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L158) |
| SereneDB / ClickHouse / NATS / Jaeger | 见 compose | SereneDB 待复核；其余为 Apache-2.0 | ✅ [docker-compose-base.yml:L106-L382](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L106-L382) |

- 🔍 以上中间件都通过网络协议访问，**不与 RAGFlow 构成衍生作品**。但有两条风险：
  - ES 8.11 的 ELv2 禁止"把 ES 作为托管服务提供给第三方"；SSPL 则对 SaaS 化提出全栈开源要求。私有化交付时建议换成 OpenSearch、Infinity 或 OceanBase。
  - AGPL 版 MinIO 分支只要不修改、并按原样提供，风险可控；若修改后通过网络提供服务，就要公开改动的源码。

### 1.5 四种使用方式
| 方式 | 能否 | 条件 / 风险 |
|---|---|---|
| 内部使用 | ✅ 可以 | 不涉及分发，GPL、AGPL、SSPL 基本不触发。仍需注意 ES 的 ELv2 条款和微软 ODBC 的 EULA。 |
| 私有化交付（向客户分发镜像或代码） | ✅ 可以，需整改 | 需要做到：(1) 保留 Apache 声明，自建第三方声明清单；(2) 处理 extract-msg（GPL-3.0）和 spaCy es 模型（GPL-3.0），建议移除；(3) 镜像中的 ghostscript（AGPL）、pandoc（GPL）提供源码获取方式，或者移除；(4) 文档引擎换成 OpenSearch、Infinity 或 OceanBase，避开 ES 的 SSPL/ELv2；(5) 核对 msodbcsql 和 Chrome 的再分发条款。 |
| SaaS 多租户 | ⚠️ 有条件 | AGPL 组件（MinIO 分支、ghostscript）一旦被修改并对外提供服务，就触发源码公开义务；ES 的 ELv2 禁止托管服务，SSPL 要求全栈开源，**必须换掉 ES**。另外开源版没有配额、计费和 RBAC（见 1.2），多租户能力不足。 |
| 二次销售（OEM / 贴牌） | ⚠️ 可以，有限制 | Apache-2.0 允许闭源修改后销售，但不能使用 RAGFlow 商标。同时要满足私有化交付的全部整改项。另需评估与官方企业版的竞争关系：Apache 协议本身不限制，属于商务风险。 |

---

## 2. 安全

### 2.1 SECURITY.md
- ✅ 内容是模板加一份旧的漏洞报告：支持版本写着 `<=0.7.0`，正文是 `restricted_loads` pickle 绕过 PoC。**没有漏洞报告渠道、联系邮箱或响应时限**。见 [SECURITY.md:L1-L74](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/SECURITY.md#L1-L74)。
- ✅ `restricted_loads` 仍然存在，见 [api/utils/configs.py:L36-L51](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/api/utils/configs.py#L36-L51)。❓ 当前白名单是否已经修复该绕过，需要人工审读。

### 2.2 默认口令与默认密钥（只记位置）
- ✅ `docker/.env` 文件头有"不要用默认密码部署"的警告，见 [docker/.env:L2-L4](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L2-L4)。实际仍为以下服务设置了**统一的默认口令**：
  - ES，[L52](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L52)
  - OpenSearch，[L62](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L62)
  - SereneDB，[L91](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L91)
  - OceanBase，[L100](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L100) 和 [L122-L123](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L122-L123)
  - SeekDB，[L136](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L136)
  - MySQL，[L144](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L144)
  - MinIO，[L179-L182](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L179-L182)
  - Redis，[L190](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L190)
  - ClickHouse，[L216](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L216)
  - **管理员默认口令** `ADMIN_DEFAULT_PASSWORD`，[L247](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L247)
- ✅ `service_conf.yaml.template` 中各服务的口令用 `${VAR:-默认值}` 形式兜底，默认值与上面相同，见 [docker/service_conf.yaml.template:L12-L85](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/service_conf.yaml.template#L12-L85)。`conf/service_conf.yaml` 中也有明文口令，见 [conf/service_conf.yaml:L12-L60](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/service_conf.yaml#L12-L60)。
- ✅ **仓库里提交了 RSA 私钥** [conf/private.pem:L1](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/private.pem#L1)，私钥口令硬编码在 [api/utils/crypt.py:L39-L49](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/api/utils/crypt.py#L39-L49)，对应公钥写死在前端 [web/src/utils/index.ts:L32](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/web/src/utils/index.ts#L32)。Go 侧同样读取这把私钥，见 [internal/common/password.go:L199-L202](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/common/password.go#L199-L202)。
  - 🔍 所有部署共用同一对密钥，登录密码的"前端加密"实际只是混淆。**必须启用 HTTPS**，并在交付时重新生成密钥对。
- ✅ SECRET_KEY 的处理：可以通过环境变量 `RAGFLOW_SECRET_KEY` 或配置文件设置（要求不少于 32 位），见 [common/settings.py:L251-L260](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/common/settings.py#L251-L260)。但真正生效的 `_get_or_create_secret_key` 把读取环境变量的代码注释掉了，改为随机生成后存入 Redis，见 [common/settings.py:L271-L288](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/common/settings.py#L271-L288)。
- ✅ 可选的落盘加密支持 `sm4-cbc`（国密 SM4），见 [docker/.env:L409-L411](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L409-L411) 和 [common/crypto_utils.py:L208-L244](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/common/crypto_utils.py#L208-L244)。默认未启用。
- ✅ compose 默认把 MySQL、MinIO（含控制台）、Redis、ES、Infinity 的端口映射到宿主机，见 [docker-compose-base.yml:L13](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L13)、[L235](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L235)、[L252-L253](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L252-L253)、[L275](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L275)。
- ✅ **开放注册默认开启**，见 [docker/.env:L343-L344](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L343-L344) 和 [common/settings.py:L321](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/common/settings.py#L321)。Admin API 端口按设计对外暴露，见 [docker/.env:L234-L236](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L234-L236)。

### 2.3 默认超级管理员
- ✅ 默认账号为 `admin@ragflow.io`。
- ✅ Web 侧的默认口令写死在代码里，见 [api/db/init_data.py:L43-L44](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/api/db/init_data.py#L43-L44)。只有带上 `--init-superuser` 参数才会创建，见 [api/ragflow_server.py:L125-L132](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/api/ragflow_server.py#L125-L132) 和 [docker/entrypoint.sh:L52](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/entrypoint.sh#L52)。
- ✅ Python admin server 首次启动时，口令优先取 `ADMIN_DEFAULT_PASSWORD`；未设置才随机生成，并写入权限为 0600 的文件，见 [admin/server/auth.py:L166-L172](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/admin/server/auth.py#L166-L172)。**而 `.env` 已经给 `ADMIN_DEFAULT_PASSWORD` 设了值（L247），所以默认部署就带固定的管理员口令。**
- ✅ Go 侧 `InitDefaultAdmin` 的默认口令也是写死的，见 [internal/admin/service.go:L1527-L1528](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/admin/service.go#L1527-L1528)。

### 2.4 鉴权
- ✅ Python 侧依次尝试三种凭证，见 [api/apps/__init__.py:L144-L225](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/api/apps/__init__.py#L144-L225)：
  1. `APIToken.beta`：分享和嵌入场景用的 token；
  2. 用 itsdangerous `URLSafeTimedSerializer` 签名的 access_token（代码里叫 jwt，但**不是标准 JWT**）；
  3. `APIToken.token`：API Key。
- ✅ 没有 Authorization 头时，回退到 session cookie，见 [api/apps/__init__.py:L110](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/api/apps/__init__.py#L110)。
- ✅ 密码用 werkzeug 的 `generate_password_hash` 存储，见 [api/db/services/user_service.py:L116](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/api/db/services/user_service.py#L116)。Go 侧依赖 golang-jwt，见 [go.mod:L37](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/go.mod#L37)。
- ✅ SSO：Python 侧支持 OAuth2、OIDC、GitHub（`api/apps/auth/{oauth,oidc,github}.py`）。**没有 LDAP、SAML 或 CAS**（在 `api/`、`common/` 中检索 `ldap|saml` 无结果）。

### 2.5 上传与代码执行沙箱
- ✅ 上传大小上限 `MAX_CONTENT_LENGTH` 默认 1GB，见 [api/apps/__init__.py:L81](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/api/apps/__init__.py#L81)。文件类型用 `filename_type` 判定。
- ✅ `sandbox-executor-manager` 的部署方式值得注意，见 [docker-compose-base.yml:L183-L207](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L183-L207)：
  - 以 **`privileged: true`** 运行，并**挂载宿主机的 `/var/run/docker.sock`**，等同于拥有宿主机 root 权限；
  - seccomp 默认关闭；
  - API token 默认为空；
  - 运行容器默认不联网（`--network none`）。
- ✅ 执行代码的容器带有以下隔离参数：`--runtime=runsc`（gVisor）、`--read-only`、`--user nobody`、`--network none`、`--memory 256m`，seccomp 可选开启，见 [agent/sandbox/executor_manager/core/container.py:L88-L120](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/agent/sandbox/executor_manager/core/container.py#L88-L120)。
- ✅ 沙箱 API token 为空时，`/run` 接口直接拒绝请求，即 fail-closed，见 [agent/sandbox/executor_manager/services/auth.py:L106](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/agent/sandbox/executor_manager/services/auth.py#L106)。
- ✅ 另有一个 `LocalProvider`，以本机子进程执行代码，只用 rlimit 限制资源，**代码注释明确说它不是沙箱边界**，见 [agent/sandbox/providers/local.py:L54-L60](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/agent/sandbox/providers/local.py#L54-L60) 和 [L295-L301](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/agent/sandbox/providers/local.py#L295-L301)。
- 🔍 gVisor 依赖宿主机安装 runsc，见 [docs/quickstart.mdx:L35](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docs/quickstart.mdx#L35)。在麒麟、统信、ARM 宿主机上能否使用 runsc，需要实测。

### 2.6 审计日志
- ✅ Go 侧定义了完整的 `OperationLog` 结构（用户、IP、操作、资源、参数），见 [internal/common/model_type.go:L53-L65](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/common/model_type.go#L53-L65)。登录时也会调用记录函数，见 [internal/handler/user.go:L134-L144](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/handler/user.go#L134-L144)。**但开源版的写入函数是空实现**，见 [clickhouse_ee.go:L44](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/engine/clickhouse/clickhouse_ee.go#L44)。
- ✅ Python 侧只有文档解析流水线的日志 `PipelineOperationLogService`，见 [rag/svr/task_executor.py:L43](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/rag/svr/task_executor.py#L43)。**没有找到**用户操作或登录的审计表。
- 🔍 结论：开源版**没有可用的安全审计日志**，满足等保 2.0 的审计要求需要自己开发。

---

## 3. 信创与国产化

### 3.1 元数据库（以代码为准）
- ✅ Python 连接池类型有 4 种：`MYSQL`、`OCEANBASE`、`POSTGRES`、`GAUSSDB`，见 [api/db/db_models.py:L797-L803](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/api/db/db_models.py#L797-L803)。迁移器同样是这 4 种，见 [L814-L820](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/api/db/db_models.py#L814-L820)。
- ✅ **GaussDB 有专门适配**：A/ORA 兼容模式下空串的语义处理、断线重试，见 [api/db/db_models.py:L72-L142](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/api/db/db_models.py#L72-L142) 和 [L546-L556](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/api/db/db_models.py#L546-L556)。`.env` 中的说明见 [docker/.env:L23-L37](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L23-L37) 和 [L158-L167](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L158-L167)。
- ✅ **Go 服务只支持 mysql 和 oceanbase**，其他类型直接报错，见 [internal/server/config/database_config.go:L49-L53](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/internal/server/config/database_config.go#L49-L53)。
- ✅ **达梦 DM、人大金仓 Kingbase、openGauss：未找到**。在 `*.py`、`*.go`、`*.yml`、`*.toml`、`*.md` 中检索 `dameng|kingbase|opengauss|dmPython` 无结果。
  - 🔍 openGauss 与 GaussDB 同源，有机会复用 GaussDB 的适配器，需要实测。
  - 🔍 金仓有 PG 兼容模式，可以尝试 `DB_TYPE=postgres`。
  - 🔍 达梦需要新增 peewee 方言，工作量较大。

### 3.2 文档引擎、向量库与对象存储
- ✅ 文档引擎支持 7 种：elasticsearch、infinity、opensearch、oceanbase、seekdb、gaussdb、serenedb，见 [common/settings.py:L399-L417](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/common/settings.py#L399-L417)。默认是 ES，见 [docker/.env:L15-L21](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L15-L21)。
  - 国产可选项：**OceanBase / SeekDB（蚂蚁）和 GaussDB（华为，需要客户自备实例）**。GaussDB 的说明见 [docker/.env:L104-L117](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L104-L117)。
- ✅ 对象存储支持 MINIO、AZURE、AWS_S3、OSS、OPENDAL、GCS，见 [common/constants.py:L229-L236](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/common/constants.py#L229-L236)。🔍 国产对象存储可以走 S3 兼容接口或 OpenDAL。

### 3.3 CPU 架构与操作系统
- ✅ 官方明确表示**只支持 x86 CPU 和 NVIDIA GPU，不提供 ARM64 镜像**，ARM 用户需要自己构建镜像，见 [docs/faq.mdx:L93](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docs/faq.mdx#L93)、[docs/quickstart.mdx:L23-L25](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docs/quickstart.mdx#L23-L25)、[README_zh.md:L193-L194](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/README_zh.md#L193-L194)。
- ✅ 发布流水线只做单平台的 `docker build`，没有 `--platform` 或 buildx，见 [.github/workflows/release.yml:L291](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/.github/workflows/release.yml#L291)。arm64 只构建了 CLI，见 [release.yml:L98-L111](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/.github/workflows/release.yml#L98-L111)。
- ✅ Dockerfile 本身有 x86_64 和 aarch64 的分支（uv、stagehand、libssl），见 [Dockerfile:L89-L94](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/Dockerfile#L89-L94) 和 [L181-L186](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/Dockerfile#L181-L186)。**但 Go 原生库（pdfium、pdf_oxide、office_oxide、onnxruntime 静态库）只下载了 linux-x64 版本**，见 [ragflow_deps/download_deps.py:L85-L101](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/ragflow_deps/download_deps.py#L85-L101)。
- ✅ Infinity 镜像带 x64 标签，见 [docker-compose-base.yml:L79](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-base.yml#L79)；官方说明 arm64 上的 Infinity 不受官方支持，见 [docs/develop/switch_doc_engine.md:L19](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docs/develop/switch_doc_engine.md#L19)。
- 🔍 **在鲲鹏、飞腾（ARM）上需要自己构建镜像，并补齐 Go 原生库的 arm64 版本**。海光是 x86 架构，可以直接用官方镜像，但需要实测。
- ✅ **oc9 = OpenCloudOS 9（腾讯牵头的国产 OS）**：基础镜像是 `FROM opencloudos/opencloudos:9.0`，见 [Dockerfile.scratch.oc9:L1](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/Dockerfile.scratch.oc9#L1)。但这份 Dockerfile **已经失效**：
  - 引用的 `requirements.txt`、`graphrag`、`plugin` 都不存在（✅ `ls` 报 No such file），且使用 Python 3.11 和 Miniconda x86_64，见 [Dockerfile.scratch.oc9:L8-L43](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/Dockerfile.scratch.oc9#L8-L43)；
  - 最后一次实质修改在 2025-07（`git log`）。
- ✅ 对应的 compose 文件开头就写明"RAGFlow 团队不维护"，用的是**个人 Docker Hub 账号的镜像** `edwardelric233/ragflow:oc9`，见 [docker/docker-compose-CN-oc9.yml:L1-L14](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/docker-compose-CN-oc9.yml#L1-L14)。**这是供应链风险。**
- ✅ 鲲鹏、海光、麒麟、统信、龙芯、openEuler：**未找到**任何适配（昇腾见下文更正）。全仓检索只在股票同义词词典中出现这些词，例如 [rag/res/synonym.json:L8210](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/rag/res/synonym.json#L8210)。
- ✅ GPU 不是必需的：`DEVICE` 默认为 cpu，见 [docker/.env:L27-L31](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L27-L31)。x86 上依赖的是 onnxruntime-gpu（有 CPU 回退），见 [pyproject.toml:L78-L79](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/pyproject.toml#L78-L79)。✅ **更正**：DeepDoc 版面识别有昇腾分支，设置 `LAYOUT_RECOGNIZER_TYPE=ascend` 时启用 `AscendLayoutRecognizer`，见 [deepdoc/parser/pdf_parser.py:L75-L89](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/deepdoc/parser/pdf_parser.py#L75-L89)。但 OCR、表格识别等其余模型仍走 ONNX，没有找到完整的昇腾 NPU / CANN 适配（初稿用中文"昇腾"检索漏掉了英文 ascend，交叉核对时发现）。

### 3.4 中文支持
- ✅ 界面有简体中文和繁体中文：`web/src/locales/zh.ts`、`zh-traditional.ts`。
- ✅ 中文分词继承自 `infinity.rag_tokenizer.RagTokenizer`（huqie 分词），见 [rag/nlp/rag_tokenizer.py:L17-L20](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/rag/nlp/rag_tokenizer.py#L17-L20)。分词词典在构建镜像时从 GitHub 或 Gitee 克隆 `infiniflow/resource`，见 [Dockerfile:L58-L69](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/Dockerfile#L58-L69)。
- ✅ 另有中文同义词和 NER 词典 `rag/res/synonym.json`、`ner.json`，以及 `cn2an`、`xpinyin` 等依赖。
- ✅ 时区默认 Asia/Shanghai，见 [docker/.env:L291](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L291)；镜像安装了 `fonts-noto-cjk` 和 `texlive-lang-chinese`，见 [Dockerfile:L54-L55](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/Dockerfile#L54-L55)。

---

## 4. 内网离线部署

### 4.1 镜像内置了什么
从 `infiniflow/ragflow_deps` 镜像拷入（✅ [Dockerfile:L17-L30](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/Dockerfile#L17-L30)）：
- DeepDoc 的 OCR、版面、表格模型，以及 `text_concat_xgb`；
- nltk_data；
- tika-server 3.3.0 jar（通过 `TIKA_SERVER_JAR=file://` 指向本地文件，避免联网）；
- tiktoken 的 cl100k 编码表。

具体下载清单见 [ragflow_deps/download_deps.py:L155-L157](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/ragflow_deps/download_deps.py#L155-L157) 和 [L267-L276](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/ragflow_deps/download_deps.py#L267-L276)。

- ✅ **主镜像不包含 embedding 或 LLM 模型**（v0.22 起），见 [docker/.env:L257](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L257)。可选的 TEI 镜像把模型打包在 `/data` 内（离线友好），见 [Dockerfile_tei:L1-L7](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/Dockerfile_tei#L1-L7) 和 [docker/.env:L268-L282](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L268-L282)。

### 4.2 运行时的外网访问点
| 访问点 | 触发条件 | 出处 |
|---|---|---|
| HuggingFace 镜像站 `hf-mirror.com` | 镜像默认设置了 `ENV HF_ENDPOINT` | ✅ [Dockerfile:L296](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/Dockerfile#L296) |
| `snapshot_download` 拉取 DeepDoc 模型 | **只在本地模型加载失败时**才触发 | ✅ [deepdoc/parser/pdf_parser.py:L100](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/deepdoc/parser/pdf_parser.py#L100)、[deepdoc/vision/ocr.py:L543](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/deepdoc/vision/ocr.py#L543)、[deepdoc/vision/layout_recognizer.py:L65](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/deepdoc/vision/layout_recognizer.py#L65)、[deepdoc/vision/table_structure_recognizer.py:L47](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/deepdoc/vision/table_structure_recognizer.py#L47) |
| `nltk.download` | 定义在 `api/validation.py` 中，**生产代码里没有找到 import 它的地方** | ✅ [api/validation.py:L35-L55](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/api/validation.py#L35-L55) |
| tiktoken 编码表 | 缓存缺失时才下载 | ✅ [common/token_utils.py:L30-L46](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/common/token_utils.py#L30-L46) |
| stagehand（Browser 组件） | Go SDK 与镜像中的版本不一致时，启动时会去 GitHub 下载，"在离线环境下会直接失败" | ✅ [Dockerfile:L128-L136](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/Dockerfile#L128-L136) |
| 遥测 | browser-use 依赖 posthog；crawl4ai、langfuse 是可选外联 | 🔍 posthog 由 browser-use 引入（uv.lock 依赖链）；import 位置 [agent/component/browser.py:L517](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/agent/component/browser.py#L517) |
| 联网类 Agent 工具（搜索、财经、Wikipedia 等约 20 个） | 用户在 Agent 中使用时 | ✅ `agent/tools/` 目录 |

- 🔍 只要镜像完整、使用 `DEVICE=cpu`、接入本地模型服务，核心的解析、检索、问答链路**可以离线运行**。建议在内网清空 `HF_ENDPOINT`，并屏蔽 posthog 和联网工具。
- ✅ **构建镜像强依赖外网**：GitHub、Gitee、nginx.org、nodesource、packages.microsoft.com、PyPI 或阿里云镜像，见 [Dockerfile:L58-L167](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/Dockerfile#L58-L167)。在内网自建镜像需要准备全量的依赖制品库。
- ✅ 官方离线文档**只有一段**：在有网环境 `docker save`，拷到内网后 `docker load`，见 [docs/administrator/upgrade_ragflow.mdx:L92-L102](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docs/administrator/upgrade_ragflow.mdx#L92-L102)。**没有完整的离线部署指南**：检索 `离线|air-gap|intranet|内网` 只命中这一处，外加 FAQ 中关于 Ollama 的一句。

### 4.3 本地模型服务
- ✅ `conf/llm_factories.json` 共收录 74 家模型供应商，其中可在本地运行的有：
  - Ollama，[L1825](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/llm_factories.json#L1825)
  - ModelScope，[L1833](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/llm_factories.json#L1833)
  - LocalAI，[L1840](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/llm_factories.json#L1840)
  - OpenAI-API-Compatible，[L1847](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/llm_factories.json#L1847)
  - VLLM，[L1863](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/llm_factories.json#L1863)
  - FastEmbed，[L2015](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/llm_factories.json#L2015)
  - Xinference，[L2022](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/llm_factories.json#L2022)
  - FunASR，[L2029](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/llm_factories.json#L2029)
  - Builtin（TEI），[L2208](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/llm_factories.json#L2208)
  - LM-Studio，[L3021](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/llm_factories.json#L3021)
  - HuggingFace，[L5395](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/llm_factories.json#L5395)
  - GPUStack，[L5403](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/llm_factories.json#L5403)
  - MinerU，[L7143](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/llm_factories.json#L7143)
  - PaddleOCR，[L7157](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/conf/llm_factories.json#L7157)
- 🔍 昇腾 MindIE、华为 ModelArts 私有化部署、DeepSeek 私有部署等国产推理框架，都可以通过 OpenAI-API-Compatible 或 VLLM 接入。没有专门的适配器。

---

## 5. 升级与迁移
- ✅ `docker/migration.sh` 用 alpine 容器对 Docker volume 做 tar 备份和还原，覆盖 mysql、minio、redis、esdata01 四个卷，见 [docker/migration.sh:L3-L16](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/migration.sh#L3-L16) 和 [L183-L186](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/migration.sh#L183-L186)。
  - **不覆盖 Infinity、OpenSearch、SereneDB 的索引卷**；还原时会因为缺少 es 备份文件而中断，见 [L61-L63](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/migration.sh#L61-L63)。
  - 🔍 也不覆盖 OceanBase 和 GaussDB。
- ✅ 版本状况：`git tag` 可见 `v1.0.0-rc1`、`dev-1.0.0` 以及大量 `dev-2026xxxx` 标签。当前仍是 0.x 版本。
- ✅ 变动规模：`git log v0.26.0..v0.27.2` 共有 **2445 个提交**，变动剧烈。筛出的相关提交包括：
  - `af4651cce security: remove leaked OAuth credentials and stop logging user secrets (#18658)`
  - `078ffca02 docs: clarify user_default_llm deprecation (#19321)`
  - `c4e989f74 fix go: migrate missing table chatchannel (#18944)`
- ✅ Release notes 中的破坏性变更：
  - v0.27.0 废弃了 GraphRAG 和 RAPTOR，UI 中已不可用，由 Knowledge Compilation 替代，见 [docs/release_notes.md:L95](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docs/release_notes.md#L95)；
  - 更早的 v0.20 曾要求所有 Agent 重建，见 [L873](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docs/release_notes.md#L873)；
  - 对象存储镜像改为 pgsty，见 [L482](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docs/release_notes.md#L482)。
- 🔍 仓库内的开发规范文件明确要求"删除兼容层、不保留 deprecated"（这是仓库资料，非本文指令）。结合 Python 与 Go 两套后端并存（`API_PROXY_SCHEME=python|go|hybrid`，见 [docker/.env:L249-L251](https://github.com/infiniflow/ragflow/blob/a024bea0cd93f39e6652a42bf84dd20c55bc560b/docker/.env#L249-L251)），预计到 1.0 之前 API 和数据结构还会继续有破坏性变更。交付时应锁定版本，并自建升级回归流程。

---

## 需人工复核清单
1. 逐包核对 Python 依赖协议（uv.lock 没有 license 元数据）。重点是 extract-msg、pcodedmp、rtfde、demjson3、gensim、datrie、hanziconv、crawl4ai，以及 spaCy 的 es、fr、pt、ja 模型。
2. 核对 Go 静态链接原生库的协议：pdf_oxide、office_oxide、pdfium-static、gomsg 的 fork、gojianfan。
3. 核对 `pgsty/silo` 的协议与来源，确认是否为 AGPL 的 MinIO 分支；核对 SereneDB、SeekDB 的协议。
4. 核对 msodbcsql 和 Chrome for Testing 的再分发条款。
5. 核对 `restricted_loads` 白名单是否已修复 SECURITY.md 中描述的绕过。
6. 实测 ARM64（鲲鹏、飞腾）自行构建镜像，以及在麒麟、统信宿主机上运行 gVisor。
7. 在完全断网环境下做端到端冒烟测试（解析、检索、问答、Agent），并抓包确认没有外联。
8. 评估从 GaussDB 适配器扩展到 openGauss、金仓、达梦的可行性。
