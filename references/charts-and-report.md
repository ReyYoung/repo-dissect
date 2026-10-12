# 图表规范与 HTML 汇总页

> 本文件是 repo-dissect 的参考资料：画图前读 1–5 节，生成 `report.html` 前读第 6 节。下文 `$SKILL_DIR` 指 SKILL.md 所在目录，`$OUT` 指本次拆解的输出目录；命令前先 `. <OUT>/_vars.sh`（见 SKILL.md 第 1 节）。

目标：读者 5 秒内看懂一张图想说什么。

## 1. 五条原则

1. **一图一结论**：每张图下面写一句图注，格式「*图 N：结论*」。说不出结论的图不画。
2. **先选对图型**：按第 2 节选图，不用一种图包打天下。
3. **能不画线就不画线**：层级、归属用位置和分组表达；只有真实的数据流、调用、先后顺序才画箭头，且箭头上写动作（「入队」「召回」）。
4. **颜色只表达一件事**：全图只有一种强调色，标"重点 / 本次讨论对象"，不超过全图元素的 1/4；状态（企业版、实验性、缺失）用**虚线框 + 文字标签**，不靠颜色区分。不用红绿表达好坏，黑白打印也要能分辨。
5. **用业务语言**：图上写「知识库管理」，不写类名、路径、参数；技术细节放图下表格。

## 2. 图型选择

| 要表达什么 | 用什么图 | 怎么出图 | 方向 / 规模上限 |
|---|---|---|---|
| 系统有哪些能力、分几层 | **分层方块图**（功能架构 / 技术分层） | 模板：JSON → SVG（`diagrams.py layered`） | 自上而下；≤ 6 层，每层 ≤ 10 个模块 |
| 谁用它做什么、依赖哪些能力 | **场景走廊图**（业务全景） | 模板：JSON → SVG（`diagrams.py corridor`） | 每行一个场景；≤ 8 行 |
| 一件事按什么步骤走 | 流程图 | Mermaid `flowchart` + 第 4 节主题 | 从左到右；≤ 12 个节点，分支 ≤ 3 |
| 组件之间如何一来一回 | 时序图 | Mermaid `sequenceDiagram` | 参与者 ≤ 6，消息 ≤ 12 |
| 一个对象有哪些状态 | 状态图 | Mermaid `stateDiagram-v2` | 状态 ≤ 8，状态值取自代码枚举 |
| 业务对象之间的关系 | ER 图 | Mermaid `erDiagram` | 实体 ≤ 12，每个只列 3–5 个关键字段 |
| 模块之间的依赖 | 依赖图 | Mermaid `graph` | ≤ 15 个节点，超出先聚合 |
| 两个方案差在哪 | 并排对比 | 同一模板画两份，差异处用强调色 | 只标差异 |

超出规模上限就拆图或先聚合。模板图由脚本按固定网格出图，离线也能渲染。

## 3. 颜色与文字（设计令牌）

| 令牌 | 默认色值 | 用途 |
|---|---|---|
| 正文 | `#181D2B` | 标题、模块名 |
| 次字 | `#59627A` | 副标题、说明、箭头 |
| 框线 | `#CCD2E0` | 方框、卡片边框 |
| 分层底 | `#F6F7FA` | 层、分组、隔行浅底 |
| **强调色（唯一）** | `#3B51D4` / 浅底 `#EEF1FE` | 重点模块、本次讨论对象 |
| 状态文字 / 浅底 | `#A25E00` / `#FCF0DC` | 只用于"企业版 / 实验性 / 仅 Go / 缺失"等标签和虚线框 |

- 一张图最多出现「中性色 + 强调色 + 状态色」三类颜色。
- 字体走系统字体栈（西文 -apple-system / Segoe UI，中文苹方 / 思源黑体 / 微软雅黑），不外链字体；数字等宽。
- 字号（按 1040 宽画布）：层名 14、模块名 13、副标题 11、标签 10。
- 模块名 ≤ 8 个汉字；副标题 ≤ 16 个字符，只写"是什么 / 有几种"。
- 同层模块等宽等高、间距统一，由模板保证，不手工对齐。
- **换强调色**：出图时加 `--accent '#RRGGBB'`（色值要加引号，否则 shell 会把 `#` 后面当注释），报告页在 `report.json` 里写 `"accent": "#RRGGBB"`，浅底色自动推出；同一份报告的图和页面用同一个色值。

## 4. 出图方法

**模板图（业务全景、功能架构）**：

1. 照着示例写数据文件 `$OUT/img/<图名>.json`（标准 JSON，不带注释）：
   - 场景走廊：`$SKILL_DIR/assets/examples/corridor.example.json`
   - 分层方块：`$SKILL_DIR/assets/examples/layered.example.json`
2. 出图：
   ```bash
   . <OUT>/_vars.sh   # 载入 OUT、SKILL_DIR
   python3 "$SKILL_DIR/scripts/diagrams.py" corridor "$OUT/img/业务全景.json" "$OUT/img/业务全景.svg"
   python3 "$SKILL_DIR/scripts/diagrams.py" layered  "$OUT/img/功能架构.json" "$OUT/img/功能架构.svg"
   ```
   字段说明：
   - corridor：`title`（一句话结论）、`columns`（固定 4 列标题）、`rows[]`：`role[]` 角色、`scene` 场景名、`desc` 一句话说明（≤ 20 字）、`caps[]` 依赖的系统能力、`ext[]` 连接的外部系统。
   - layered：`title`、`layers[]`：`name` 层名、`groups[]`：`title`（可选）、`dashed`（可选，true 表示虚线分组，如"企业版能力"）、`modules[]`：`name`、`sub`（可选副标题）、`status`（可选）、`tag`（可选，右上角状态标签文案，如 "仅 Python""仅 Go"）。
   - `status` 取值：`focus`（核心，强调色）、`ee`（企业版，虚线框灰字，带"企业版"标签）、`beta`（带"实验性"标签）、不填为普通。放在 `dashed` 分组里的模块不再重复显示标签。
   - `legend[]`（可选图例）每项二选一：`["box", 样式, 说明]`，样式为 `"focus"`、`null`（普通）或 `"ee"`；`["pill", 标签文案, 说明]`。
   - 结构写错时脚本会报出缺少的字段，对照示例改正即可。
3. Markdown 中这样引用，图注紧跟在图后、中间空一行（`report.html` 靠这个格式把 SVG 内联进页面，图注变成图下说明）：
   ```markdown
   ![图 2：一句话结论](img/功能架构.svg)

   *图 2：一句话结论。数据源：`img/功能架构.json`。*
   ```
4. 能运行浏览器、且你能看图时，打开 SVG 截一张图自查文字溢出、重叠、对齐；做不到就跳过，并遵守第 1、3 节的字数上限。

**Mermaid 图（流程、时序、状态、ER、依赖）**：每个代码块第一行加统一主题，只允许 `focus`、`missing` 两种样式类，不给单个节点自定义颜色（换了强调色时把下面的 `#3B51D4`、`#EEF1FE` 一起换掉）：

```
%%{init: {"theme": "base", "fontFamily": "-apple-system, Segoe UI, PingFang SC, Noto Sans CJK SC, Microsoft YaHei, sans-serif", "themeVariables": {"fontSize": "13px", "primaryColor": "#FFFFFF", "primaryBorderColor": "#CCD2E0", "primaryTextColor": "#181D2B", "lineColor": "#59627A", "secondaryColor": "#F6F7FA", "tertiaryColor": "#F6F7FA", "clusterBkg": "#F6F7FA", "clusterBorder": "#F6F7FA", "actorBkg": "#FFFFFF", "actorBorder": "#CCD2E0", "noteBkgColor": "#FCF0DC", "noteBorderColor": "#A25E00"}}}%%
flowchart LR
  classDef focus fill:#EEF1FE,stroke:#3B51D4,stroke-width:1.6px,color:#2D3FAE
  classDef missing fill:#FFFFFF,stroke:#A25E00,stroke-dasharray:4 3,color:#59627A
```

Mermaid 常见渲染错误（写完逐条自查）：
- 节点文字含中文、空格或符号时加引号：`A["配置加载"]`；
- 标签里不写尖括号占位符（`<id>` 会被安全过滤吞掉），改用 `{id}`；
- `erDiagram` 实体名用英文模型名，中文含义放图下表格；属性**一行一个**，不能用分号写在一行；
- 校验：生成 `report.html` 时脚本会逐张渲染 Mermaid（static 模式），语法错误会打印出图号和报错，按提示改正后重新生成即可。

**线框图**（需要示意页面结构时）：只用灰阶，强调色只给主操作按钮和当前选中项；文字只写真实的导航和按钮名，正文用灰条代替；标注用编号圆圈 ①②③，说明写在图注里；一张线框只画一个页面状态。

## 5. 出图检查清单

1. 图注能用一句话说出结论吗？
2. 图型是否按第 2 节选择，是否超出规模上限？
3. 有没有不表达真实流向的连线？有就删。
4. 强调色是否只用在重点上？状态是否都有文字标签？
5. 模块名是否全是业务语言、长度达标？
6. 黑白打印、手机竖屏（横向滑动）下还能看清吗？

## 6. HTML 汇总页 → `report.html`

`build_report.py` 只用 Python 标准库，把 `report.json` 和各层 Markdown 合成一个单文件网页，版式固定，不要手写或逐份手改 HTML。

**版式**（脚本自动完成，这里说明是为了写好 Markdown 和 `report.json`）：

- **布局**：左侧「报告目录」侧边导航，当前章节高亮；中间内容区；右侧「本章目录」锚点目录，随当前章节切换（宽屏才显示）。手机上侧边导航收成顶部横向标签，图表横向滑动查看。
- **首屏**（先结论后依据）：面包屑 → 标题与一行辅助信息 → 结论卡片（结论标签 + 一句话结论 + 不超过 3 条条件；右侧放仓库、版本、场景、运行验证等）→ 3–4 个关键数字 → 需要提醒的事项（警告提示条）。
- **章节顺序**：选型评估、多项目对比类目标先放 R、Q、`compare.md`，再放 L0–L2；架构学习、写教程类按 L0 起的自然顺序；证据明细类文档放最后，标为附录（默认折叠）。
- **自动转换**：
  - 表格和正文里加粗的结论词（满足 / 部分满足 / 需二次开发 / 仅企业版满足 / 不满足 / 推荐 / 有条件推荐 / 不推荐），以及单元格里只有结论词的，转成状态标签；
  - ✅ 🔍 ❓ 转成「事实 / 推断 / 待确认」小标签；Markdown 引用块转成信息提示条；
  - 标题以「附录」开头的小节（文件里的 `##` 或 `###`）自动折叠；
  - 按第 4 节格式引用的模板图内联为 SVG；Mermaid 图也打包进页面，**离线可看、不加载任何外部资源**（见下方"Mermaid 离线方式"）；
  - 每张图下有「下载 SVG / 下载 PNG」；右上角「打印 / 导出 PDF」会展开所有折叠后打印。
- **样式**：页面浅灰底、白色卡片、细边框、圆角；状态标签用语义色（成功绿、信息青、警告橙、错误红），且一定配文字；不外链字体。

**做法**：

1. 各层 Markdown 的标题约定：每个文件以唯一一个 `# 标题` 开头（页面上变成带编号的章节标题），正文小节用 `##`、`###`（进入右侧"本章目录"）。
2. 照着 `$SKILL_DIR/assets/examples/report.example.json` 写 `$OUT/report.json`（标准 JSON）。字段：
   - `title`、`subtitle`、`crumbs[]`（面包屑）；
   - `verdict`：`level` 用「推荐 / 有条件推荐 / 不推荐」之一时显示对应颜色，非选型目标可写「架构学习」等（中性色）；`summary` 一句话结论；`points[]` 不超过 3 条；
   - `meta[]`：`[名称, 值]`，放仓库、版本、Commit、场景、运行验证；
   - `stats[]`：`[数值, 标签, 补充说明]`，3–4 个；
   - `notice`（可选）：`{"tone": "warn", "text": "..."}`；
   - `sections[]`：`[文件名, 目录名]`，附录加第三项 `"appendix"`；
   - `footer`；`accent`（可选，强调色 `#RRGGBB`）；`product`（可选，左上角名称，默认"开源项目拆解"）。
3. 运行 `. <OUT>/_vars.sh && python3 "$SKILL_DIR/scripts/build_report.py" "$OUT"`。报错时按提示补字段或文件。
   - **Mermaid 离线方式**（默认 `auto` 自动选择）：有 Python Playwright 时用 `static`，在本地把每张 Mermaid 图预渲染成静态 SVG，报告体积小，并报出语法错误；没有时用 `inline`，把随附的 `assets/vendor/mermaid.min.js`（约 2.7 MB）打包进报告，打开时在浏览器里渲染。可用 `--mermaid static` 或 `--mermaid inline` 指定。两种方式都不联网。
4. 检查：
   - 能跑浏览器（如 Playwright）时：1440 宽和 390 宽各截一张，确认无脚本报错、Mermaid 图都已显示为图形（不是源码）、无整页横向滚动、模板图下载 PNG 可用、侧边导航随滚动高亮；
   - 不能跑浏览器或你看不了图时：至少确认脚本无报错、`report.html` 里每个 section 都在、模板图已内联（搜 `<figure class="diagram tpl"`）。

**写教程目标**：微信公众号、小红书等平台不渲染 Mermaid，文章里的图从 `report.html` 下载 PNG；代码片段每段不超过约 20 行；Demo 复现步骤必须实际跑通过，跑不通的标 ❓。
