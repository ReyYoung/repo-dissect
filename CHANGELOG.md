# Changelog

English · [简体中文](CHANGELOG.zh-CN.md)

## [1.7.1] - 2026-10-15

When Codex and WorkBuddy dissected the same project (Tencent/teamai-cli) with 1.7.0, the four front-page stat cards looked very different. Partly the users picked different mechanisms; partly the rule only said "show 2–3 mechanisms for 架构学习" with no fixed card format, so the same mechanism got two names ("投递对账" vs "交付账本"), and one report showed concrete facts while the other showed concept words that only make sense after reading the body.

### Changed

- **Front-page stats follow a fixed format per primary goal**, always 4 cards:
  - 架构学习, 写教程, 二次开发: 3 mechanism cards labelled `机制 · <name from the L2 candidate table>`, with the most concrete fact as the big value (a number chain, key constant or decision rule) and the table's "why unique" as the note; mechanisms the user chose come first;
  - 选型评估, 需求对照: requirement fit, main risk, maintainer risk;
  - 多项目对比: one card per project; 产品与方案参考: three product designs;
  - the 4th card is always "root licence · activity", with numbers from `repo_stats.py`.
- **`report.json` gains a `goal` field** for the primary goal, used by the front-page checks.
- **`build_report.py` hints:**
  - a mechanism card whose name is not in the L2 candidate table is flagged, so one mechanism has one name everywhere;
  - selection advice such as "试点" or "推荐采用" on the front page of a 架构学习 or 写教程 report is flagged.

### Fixed

- ✅ 🔍 ❓ in the front-page conclusion and the notice bar now render as the same "事实 / 推断 / 待确认" tags as the body, instead of raw symbols.
- `report.example.json` gains `goal`, and its commit count now comes from `repo_stats.py`.
- Regression tests now number 24.

## [1.7.0] - 2026-10-15

Based on the retrospectives WorkBuddy and Codex each wrote after dissecting the same project (garrytan/gstack) with 1.6.1. WorkBuddy found several cases where the scripts gave a false "pass", with reproducible cases; the worst was `checklinks.py --fix` rewriting 12 continuation references to the wrong file and still reporting "0 problems". Codex pointed out environment conclusions stated too broadly, report checks not tied to a specific build, and Mermaid packaging being mistaken for rendering.

### Added

- **Regression tests, `tests/run_tests.py`**: 21 cases that feed the scripts deliberately broken documents and check each problem is reported. Needs only Python and git, runs offline; the 1.6.1 scripts fail 16 of them.
- **Link text vs anchor check**: a permalink whose text says `a.py:L182-L186` while the link points to `#L180-L186` is reported (a common slip when a range is edited by hand).

### Fixed

- **Continuation reference attribution.** A continuation used to take the nearest full path anywhere in the same section, even across a table or another paragraph, and could land on the wrong file. Now:
  - it only uses a path from the same paragraph, table row or list item;
  - when two different files appear earlier in that block, it reports "ambiguous attribution"; links to other repositories (compare mode, dependencies) and broken references count too, so a continuation never skips past them to an earlier path;
  - a bare `>` line in a blockquote and the line after a heading also start a new block.
- **`--fix` no longer rewrites silently**: it lists every rewrite (line numbers match the original file, including after code blocks), lists continuation expansions separately with a reminder to re-read the sentence, runs a read-only check again afterwards, and keeps the file's line endings (CRLF / LF).
- **Universal-claim list**: when only some documents in a folder are checked, entries for the others are kept instead of the list being overwritten or deleted.
- **L4 six-block check:**
  - headings such as "没精读的关键机制" no longer count as the core-mechanism block;
  - the input/output block is no longer satisfied by a bare "输出";
  - files named `04_`, `4-` or containing 核心模块 / 精读 are checked too, with a hint to use the `04-` prefix.
- **`build_report.py` prints the file size in bytes** (it printed a character count) and a content checksum computed from the input files, so it stays the same while the content does.

### Changed

- **When the user picks more mechanisms than the limit**, there is now a defined approach: do not refuse or silently drop any; group them into directions and run "one L3 plus one L4 per direction", telling the user the cost first. Each L4 lists the mechanisms in its own direction that were not covered, and `index.md` records the overall coverage.
- **When L4 overturns an L2 statement**, L2 is corrected and the L4 notes the difference.
- **Selection basis**: when deep dives exist, `checklinks.py` hints if the basis reads like the agent's own choice ("我判断", "我决定") or, for a large repo, quotes no words from the user.
- **The universal-claim list** now also absorbs the separately printed "absolute wording" hint, split into strong and weak, with a count at the top; limits are 8 per document and 40 in total, strong first.
- **References skipped as port numbers** (`:8080`) are listed so misjudgments can be spotted.
- **Size threshold**: content-heavy projects with more than about 50,000 Markdown lines count as large; `repo_stats.py` prints a size verdict.
- **`build_report.py` hints:**
  - inline mode now says the diagrams were not rendered during the build and should be viewed in a browser before delivery; static mode states that each was rendered;
  - it flags "等待选题" left in `report.json` when deep dives exist.
- **Report checks in `index.md`** name the content checksum they apply to; after the content changes, older results are marked as applying to an earlier version. Mermaid rendering and visual checks are recorded separately. The example's `index.md` follows the new format.
- **`check_env.py` states its scope:**
  - the file-sandbox row says "temp directory not blocked (other paths not tested)" instead of "unrestricted";
  - network rows say "not reachable from this command environment";
  - Docker permission errors get OS-specific advice (on macOS usually a sandbox limit).
- **Working habits:**
  - find paths before reading, and keep `git log` to subjects and a limited count;
  - run key steps separately and check each result;
  - do not write one-off scripts to assemble the report, and update leftover "等待选题" text after each stage.
- **README** gains a "Regression tests" section.

## [1.6.1] - 2026-10-15

Codex, running 1.5.1, again did not offer a skill update, yet updated fine when the user asked it to check. Codex's own diagnosis: the environment check failed inside its sandbox (dead proxy port, DNS failure) and reported "latest version unknown"; afterwards it reached GitHub through its GitHub connector and an approved command outside the sandbox and fetched the source, but never rechecked the skill version. The command environment that runs the scripts can have different network access from the agent's other tools.

### Changed

- **Try other channels before giving up.** When the check cannot reach GitHub, the agent first checks another way: a GitHub connector or API tool on `repos/ReyYoung/repo-dissect/tags`, a web-reading tool on the tags page, or rerunning `version_check.py` with network permission as the environment allows. Only if all of these fail does it tell the user the latest version cannot be confirmed. The check output, recheck message and SKILL.md all say this.
- **The post-fetch recheck no longer depends on a saved record.** Previously it ran only if an "unknown" result had been saved at the start; in a sandbox the home directory is often read-only, nothing was saved, and the recheck never ran. Now:
  - the record falls back to the system temp directory when `~/.cache` is not writable;
  - after a successful fetch, `fetch_repo.py` rechecks whenever no recent definite result is found.
- **Manual recheck:** when the code was fetched with git clone or another channel, run `version_check.py` the same way the fetch succeeded (same network permission, same tool).
- The version result in `index.md` now lists which channels were tried.

## [1.6.0] - 2026-10-15

Based on two 1.5.x reports on the same project (Open WebUI, same commit and goal) by Codex and WorkBuddy, and a review that checked each disputed claim against the source. Every code link in both reports resolved, yet they still had inconsistent statistics, local observations turned into universal claims, different execution paths treated as one, function definitions cited without checking the call path, and contradictions within a chapter. This release moves the error-prone steps into scripts or fixed procedures.

### Added

- **`scripts/repo_stats.py`: repository statistics with fixed definitions.** Run once at the start of L0; results are saved to `_stats.json`, and the report takes these numbers from it:
  - file count, and physical lines per language (lock files, vendored directories, minified output and translation files listed separately);
  - commits in the last year, with the window anchored to the HEAD commit date, so a given commit always gives the same result;
  - author share, with all commits in the window as the denominator; suspected aliases are listed, not merged;
  - tests: test code and test fixtures counted separately; CI steps that run tests, and steps that call another repo's workflow or check out a separate test repo.
- **Universal-claim list.** `checklinks.py` writes sentences with universal wording (一律, 唯一, 只能, 从不, 无回归…; in main-flow and deep-dive docs also 所有, 全部) to `_全称句清单.txt`, up to 60, skipping those that state a scope. Before delivery each is checked against the same chapter's body, tables and open questions. Spot checks after merging subagent work also pick from it.

### Changed

- **Three new rows in the negative and universal claims table of the common-misjudgment list:**
  - "no tests / no regression coverage": check CI and external test repos; few in-repo tests only supports "few in-repo tests";
  - "X is the only deciding field": read the whole branch and list every field involved;
  - "failures always return X / such requests always take path Y": check each error site and each path.

  The "only freed by restart" row now also covers caches and registries that "only grow".
- **Path variants.** The L2 mechanism table gets a "path variants" column (default / legacy / deployment variant / per backend). L3 and L4 claims say which path they describe, and list every condition that selects a path.
- **Call relations must cite the call site.** Citing only the callee's definition does not show that the path calls it. L4 core mechanisms are traced through register → select → execute → result → release.
- **Maintainer concentration** uses all commits in the window as the denominator and states the window; suspected aliases are not merged until verified.
- **Front-page stats follow the primary goal.** For 架构学习 and 写教程, show 2–3 key mechanisms worth learning instead of stack names. Verification notes such as V0 appear once, in the front-page notice and the report notes.
- **`build_report.py`:**
  - the universal-wording hint now also covers front-page stat labels and notes;
  - sections whose heading starts with 「证据明细」 are collapsed, so the body keeps short conclusions and long evidence lists go there.
- **`index.md`** gains two fields: the agent and model used (when available) and the statistics window.
- **Other places now share the same numbers:** the size threshold and the hotspot window use `repo_stats.py`; `_vars.sh` gains `SRC` (the source directory).
- **The example report's** commit, author and concentration figures now come from `repo_stats.py`.
- **README**: the Updating section adds a one-line update prompt to send to your agent.

## [1.5.1] - 2026-10-14

In one Codex run the agent did not mention a skill update, while WorkBuddy did. When the version check could not reach GitHub, the script only showed a "skipped" row in the environment table and exited with 0, the same as "up to date". The rules also only asked the agent to speak up when a newer version was found. This release treats "unknown" as its own state.

### Changed

- **"Unknown" is a separate state.** `version_check.py` reports one of: newer available, up to date, unknown, skipped. Unknown exits with 20 (previously 0) and gives the reason.
- **The result is always printed and always passed on.** The "技能版本" line at the end of `check_env.py` now appears every time, not only when a newer version exists. When the latest version is unknown, the agent tells the user in its first question: local version, latest unknown, carrying on with the current one. The run does not stop for this.
- **The version check uses the network route found by the environment check.** It goes through a local proxy when direct access fails, and goes direct when a configured proxy is dead, for that one command only. Run on its own, `version_check.py` retries once direct and once through each local proxy after a first failure. A new `--proxy URL|none` option is available, and `--update` reuses the route that worked.
- **One automatic recheck after fetching code.** An unknown result is recorded in `~/.cache/repo-dissect/version-check.json`. After a successful fetch, `fetch_repo.py` checks again and prints a "技能版本复查" line:
  - a newer version found: the agent asks whether to update; if the user agrees, it updates, re-reads SKILL.md and carries on (the fetched code is kept);
  - still unknown: no further retries.

  When the code is fetched with `git clone`, the agent rechecks once by hand as SKILL.md describes.
- The version field in `index.md` now records the check result: up to date, newer and whether it was installed, or unknown with the reason and the recheck result.

## [1.5.0] - 2026-10-14

Based on three 1.4.x runs on the same project (WorkBuddy on Mac and Windows, Codex) and Codex's review of them. Every code link in all three reports resolved, yet several conclusions were stronger than the evidence, and summaries contradicted the body. This release adds light rules and script hints, not new ledgers.

### Added

- **Key-claims table.** `index.md` gains a 「关键结论核对表」 (claim | scope | evidence | counter-examples checked) covering the front-page conclusions and key negative, universal, numeric, licence, data-flow and lifecycle claims. It is filled after the body and the open questions, and the front page is taken from it. `checklinks.py` gives a hint when it is missing.
- **Verification levels V0–V4** (static reading, pure-logic tests, mocked dependencies, real dependencies, target platform). "Read a test assertion" is V0, not "tests pass". `index.md` also records report QA results as passed / failed / not done.
- **Script hints in `build_report.py`:**
  - Mermaid size: sequence participants and messages, flowchart and graph nodes, states, ER entities, against the documented limits;
  - front-page stats that look like production metrics;
  - front-page conclusions that use universal words without a scope.
- **Version stamp.** The skill version is written into the report footer and the "报告说明" section.
- **Domestic-stack check (L5 item 7).** When the scenario has a 信创 / domestic-stack constraint, each database, middleware and model-API component is assessed for whether it can be replaced by a domestic Chinese product, and at what cost:
  - the access path is checked first (ORM or dialect layer vs direct calls, dialect-specific SQL, whether the model API takes a configurable `base_url`);
  - cost is given as S/M/L with stated boundaries, and data migration gets its own row;
  - a vendor's "compatible with X" claim is checked feature by feature against what the project actually uses, and anything not run is marked "not verified".

  When only the selection assessment runs (no L5), the table goes into `06-选型评估.md`.

### Changed

- **Numbers** must state what was counted, the scope and dedup rule. Counts from different bases are not merged. Estimates stay off the front-page stats and are labelled "粗估" in conclusions.
- **Negative and universal claims** are written as "within X, using Y, Z was not found". `references/layers.md` adds checks for six common ones: no config file, everything under one mechanism, only freed by restart, no queue, a value never used in production code, and a generated file not checked by CI.
- **Licences:** top-level and component licences are recorded separately. MPL, EPL and LGPL are weak copyleft and CC-BY requires attribution, so none of them is "permissive"; unknown means unknown.
- **L2** lists four boundaries separately: configuration sources, resource ownership (owned process, attached session, external service), queues (separate broker vs in-process) and how resources are released.
- **L3** sequence diagrams cover one stage each. "Create an object" is kept apart from "start a process", and L3 is updated when L4 corrects it.
- **L4:**
  - "A is derived from B" claims are checked against actual inputs and outputs;
  - weaker alternatives must be labelled as a different design;
  - goals 架构学习 and 写教程 add a short reading route with an example and a counter-example.
- **Subagents** receive environment facts (user platform, host, target platform, verification done) from the main agent instead of guessing. After merging, the main agent reconciles front page, body and open questions, keeps L3 and L4 consistent, and recounts the statistics. Spot checks cover a positive fact, a negative claim and a cross-module edge.
- **Example:** the ER diagram is trimmed to 12 entities, the 7-participant sequence diagram is split into ingest and query, a 13-node flowchart is merged to 12, and `index.md` gains the new sections.

### Fixed

- Leftover references to "两个决策点" (renamed in 1.4.0) now point to "需要用户拿主意的地方".
- The change summary shown with an update prompt no longer shows a bare two-word title; it adds the first clause after it.

## [1.4.1] - 2026-10-14

### Changed

- Updating with consent. When the environment check finds a newer version, the agent now asks in its first question whether to update before starting, listing the main changes read from the new version's changelog.
  - If the user agrees, it runs `version_check.py --update`, re-reads SKILL.md, re-runs the check and starts with the new rules.
  - If the user declines, does not answer, or the run is unattended, it continues with the current version.
- `scripts/version_check.py --update`:
  - **git install:** runs `git pull --ff-only`. It refuses and lists the files when the skill folder has local changes.
  - **Other installs:** fetches the release tag (git clone, falling back to the GitHub archive) and checks its `VERSION`. It backs up the old files to `~/.cache/repo-dissect-backup/`, then replaces only the skill files: `SKILL.md`, `VERSION`, `agents/`, `references/`, `scripts/` and `assets/`.
- `index.md` records the skill version used, the latest version on GitHub, and whether the skill was updated at the start.
- README: the "Updating" section describes the new flow and the manual command.

## [1.4.0] - 2026-10-14

Based on two runs of 1.3.0 on FastGPT (Codex and WorkBuddy + DeepSeek), their evaluation reports, and a report from WorkBuddy on squeezed tables.

### Changed

- **Who picks the deep-dive modules.** SKILL.md §0 now lists the points where the user decides: the start-of-run question, the L0 gate, and, for large repositories whose goal includes L3/L4, a stop after L2 to choose 1–2 mechanisms from the candidate table. Other rules:
  - The agent's recommendation, an answer to a different question, silence or elapsed time do not count as a choice.
  - Only an explicit hand-over ("模块你来挑") lets the agent choose, and the user's words are recorded. "完整拆解", "直接跑完" and unattended mode alone do not count.
  - Without a choice, the run delivers L0–L2 with the candidate table, marked "等待选题".
  - Small repositories still self-select from the table and say so.
  - For large repositories the L0 gate is reported together with the selection.
- **Goal and use scenario are separate.** A scenario such as private delivery or SaaS only decides which licence and deployment checks to run inside existing layers. It no longer adds an R layer or changes the primary goal. Report sections follow the primary goal.
- `index.md` records "选题依据": the user's words, the delegation, or "小仓库，按候选表自选". `checklinks.py` reports an error when 04- documents exist and `index.md` lacks this line or still says "等待选题".
- `references/layers.md`:
  - **New "常见误判清单":** eight kinds of conclusion that need more than the obvious evidence: required vs optional, community vs commercial, publishable vs published, costly vs impossible to extract, stable vs unverified, licence risk, painless upgrades, and enterprise features behind a flag.
  - **L1:** maturity needs a source and is kept apart from whether this run verified it. Edition ownership is traced from UI through API to the local or commercial implementation.
  - **L5:** reuse advice is written as "if the client needs X → Y", S/M/L estimates state their boundaries, and "hard to extract" is kept apart from "cannot be extracted".
  - **R:** licence scans state their scope (ecosystems, lock file vs registry metadata, unknown and failed packages, what was not covered).
  - **Community data:** figures state their basis, e.g. `open_issues_count` includes PRs.
- Reports:
  - **Tables:** tables with 3 or more columns get content-based column widths. Each column keeps a minimum width so Chinese text is no longer squeezed to one or two characters per line, and spare width goes to the columns with more content. Cells may break long paths, and printing uses proportional widths.
  - **Wider text area:** the right-hand table of contents becomes the "目录" button below 1500 px.
  - **Windows:** the page detects Windows and uses 15 px body text, darker text and slightly larger small text. Font stacks add Microsoft YaHei UI and Consolas or Cascadia Mono for code, which previously fell back to Courier New.
  - **Sections:** `build_report.py` warns when `index.md` is listed as a report section.
- `run_project.py plan` finds compose files with non-standard names (`docker-compose.pg.yml`, `docker-compose-milvus.yml`) up to six levels deep, skipping hidden and dependency folders. Paths containing dev, test, template, middleware and similar words are ranked last. When it picks a non-standard file, the card says so and lists the alternatives.

## [1.3.1] - 2026-10-14

### Added

- Update check. A `VERSION` file records the installed version. `scripts/version_check.py` compares it with the latest release tag on GitHub, falling back to `git ls-remote` when the API is unreachable, and `check_env.py` runs it first.
  - When a newer version exists, the check shows how to update: `git pull --ff-only` for a git install, or a one-line prompt for the agent otherwise. It warns first if files in the skill folder were modified locally.
  - It never downloads or replaces anything. SKILL.md tells the agent to mention the update once when presenting the plan and to keep using the current version.
  - It is skipped silently when offline. Set `RD_NO_UPDATE_CHECK=1` to turn it off.
- SKILL.md: the agent must not modify the skill's own files during a run. Problems are worked around in the output folder and noted in `index.md`.
- README: an "Updating" section. The manual install commands now copy `VERSION` too.

## [1.3.0] - 2026-10-13

Based on feedback from two real runs (Codex on Windows and WorkBuddy + DeepSeek, both on Databuddy) and a review of their reports.

### Added

- `scripts/fetch_repo.py`: gets the source when `git clone` is unavailable or very slow.
  - Tries, in order: `git clone`, one GitHub archive download (codeload, a single connection), then file-by-file download (jsDelivr, falling back to raw.githubusercontent.com) over reused connections with retries. When the connection is slow (over 5 s per TLS handshake), the archive is tried first.
  - Every non-git result is checked file by file against the GitHub tree (git blob SHA-1). Files and their hashes are written to `src/.rd-manifest.json`.
  - Also supports `--only <dir>`, `--dry-run` (file count and size, no download), `--from-archive` for a source ZIP the user downloaded, and resuming an interrupted file-by-file download.
  - Uses the proxy from the environment, then a direct connection. If neither works, or both are slow, it tries common local proxy ports (Clash 7890/7897 and others) for that command only. A dead git proxy setting (`http.proxy` or a GitHub-specific `http.<url>.proxy`) is overridden per command and never changed; environment proxies are dropped from git's environment when going direct.
  - Git and archive downloads go to a temporary folder and replace the output folder only on success, so a failed attempt never wipes a partial file-by-file download. Archive paths are checked so nothing is written outside the output folder (including drive letters and reserved names on Windows). Files marked `export-subst` and truncated GitHub tree listings are recorded as not verified instead of failing the check.
  - `RD_GITHUB_MIRROR` (or `--mirror`) takes a mirror the user trusts; no third-party mirror is built in, and mirror results are verified against the pinned commit.
  - Certificate checks are never turned off.
- `check_env.py`:
  - measures TCP + TLS time to github.com and reports "slow but usable" separately from "unreachable";
  - reports untrusted certificates with a fix that keeps verification on;
  - reports a global git proxy or environment proxy that points to a dead port;
  - finds a working local proxy and suggests using it per command;
  - adds a final "取代码" line saying whether to use `git clone` or `fetch_repo.py`.
- `diagrams.py` checks a diagram before writing it and exits with 1 without writing the file. It checks:
  - limits: layers ≤ 6, modules per layer ≤ 10 (dashed groups counted separately), scenario rows ≤ 8;
  - whether layer names, module names, subtitles, scene text and chips fit their boxes;
  - whether every text element stays inside the canvas.
  `diagrams.py check <json|svg>` runs the checks alone.
- `run_project.py plan` recognises a compose file that only starts infrastructure (databases, caches, queues, object storage, search) and has no app service or web port. Images are matched on whole names, and an image that is the analyzed project itself does not count. It then says the app has to be installed separately and cannot be screenshotted, instead of "ready". Admin ports of infrastructure (e.g. MinIO on 9000) are no longer taken as the web address.
- Report:
  - two closing sections from `report.json`: `pending` (open questions) and `about` (scope, method, production statistics, evidence limits);
  - a "目录" button at widths up to 1280 px that opens the current chapter's headings, and on phones the chapter list as well;
  - the active phone tab scrolls into view;
  - wide tables show a scroll hint and keep the first column fixed;
  - wide diagrams get a fit-to-width / original-size toggle, fit by default on phones.
- Analysis rules (SKILL.md, `references/layers.md`):
  - L2 ends with a table of 5–8 candidate mechanisms (location, why it is distinctive, relevance to the goal, evidence available). L3 and L4 pick from it, and each L4 document lists the important mechanisms it leaves out.
  - When the user picks a module, they are told what that excludes.
  - L4 requires six blocks: problem and inputs/outputs, core mechanism, failure boundaries, trade-offs with alternatives and evidence, where it applies, technical debt.
  - With several goals, the first is primary and the others add only the layers they need.
  - Conclusion self-check: can the code prove it, is there a counter-example, is an inference written as fact. Absolute wording is avoided.
  - A fixed open-questions section in `index.md`.
  - The scale threshold also counts files (> 2000) and download size (> 50 MB). The scale question goes into the same single question as the run card.
  - Front-page stats show project facts, not production metrics.

### Changed

- `checklinks.py`:
  - **Paths:** paths containing `( )` and `[ ]` (e.g. Next.js `app/(main)/[id]/page.tsx`) are recognised in both permalinks and `path:line` references. Paths that look truncated are reported.
  - **Continuation references:** `` `:1234` `` and `` `:120-140` `` reuse the last full path in the same section and are verified; `--fix` expands them to permalinks.
  - **Archive mode:** a source tree without `.git` is checked through `.rd-manifest.json`, including the commit, with no change to the command. An archive without a recorded commit is accepted with a "version not checked" note.
  - **False positives:** host names with a port (`github.com:443`) and `` `:8080` `` right after words like 端口 / 监听 / port are no longer read as references; `./path` is resolved correctly.
  - **L4 blocks:** `04-*` documents missing any of the six required blocks are errors.
  - **"✅ without reference" hint:** it now also fires when only one condition holds. Headings, table separators, lines with a directory permalink, and lines with command evidence are skipped.
  - **New hint:** absolute wording (必然, 绝对, 保证, 100% 可靠 …).
- Report styling:
  - tag text colours reach at least 5:1 contrast;
  - small text is at least 11.5 px;
  - the active nav item carries `aria-current`;
  - focus outlines are visible;
  - reduced-motion preferences are respected;
  - anchors are no longer hidden under the sticky phone navigation;
  - the print / PDF button stays on phones;
  - printing from the browser menu also expands collapsed sections and scales wide diagrams to the page.

## [1.2.2] - 2026-10-13

### Added

- The report sidebar and browser tab show the repo-dissect logo (`assets/brand/`), embedded in `report.html`; `"logo"` in `report.json` replaces it with your own image.

### Fixed

- CHANGELOG: stray backslashes before inline code in the 1.2.1 entry.

## [1.2.1] - 2026-10-13

Fixes from a real run in an agent with a file sandbox (WorkBuddy on macOS, Dify).

### Fixed

- Registry reachability is now checked by the Docker daemon itself (Engine API `/distribution/<image>/json` over the local socket) instead of from the agent's process. The daemon may use a different network path — OrbStack follows the macOS system proxy — so the old check could report "registry unreachable" while Docker could pull fine. On a Mac where Docker really can't reach the registry, the card now suggests starting the proxy and restarting OrbStack (or `orb config set network_proxy`) and recommends re-checking rather than handing off.
- `run_project.py` no longer fails when the agent's file sandbox rejects `mkdir` on an existing directory (`PermissionError` EEXIST even with `exist_ok=True`); re-running `plan` and `handoff` works.
- `plan` is read-only and takes seconds: it no longer copies the project or writes `.env`. Compose files are parsed with the project's own `.env.example` as the variable file; when a service requires `env_file: .env`, parsing happens in a symlink mirror under `run/probe` that is removed afterwards.
- If `plan` hits an unexpected error, it still writes a decision card (reason in plain language, hand-off recommended) and exits with 3 instead of a traceback.
- When compose parsing falls back to the regex parser (e.g. the sandbox blocks reading `.env.example`), the card no longer lists images, ports or registries from it — the regex parser cannot tell which profile services are active — and offers "fix and re-check" instead of showing "ready".
- Cleanup also removes containers, networks and volumes by project label, so a `--keep` stack is cleaned even if the plan or work copy is gone.

### Added

- `run_project.py prepare`: builds the work copy and `.env` on its own, so agents that need interactive file approval can run it in the foreground and put `run` in the background. `run` does the same step first. The copy uses APFS cloning on macOS, skips files the sandbox refuses, and a failed `.env` generation is logged instead of aborting; compose then uses the template for variables.
- `plan` drafts `run/pages.json` from frontend routes (Next.js `app/` and `pages/`, React Router / Vue Router configs including `Routes.X` constants), skipping dynamic and login/install pages.
- The decision card lists the images that are missing locally.
- `check_env.py` probes the two sandbox behaviours (mkdir on an existing directory, `.env` file access) in a temporary directory.
- `checklinks.py --show` prints the code line each reference points to, for spot-checking references that are in range but point at the wrong line. Lines whose evidence is a command in backticks (`git shortlog …`, `rg -n …`) no longer get the "✅ without reference" hint.

## [1.2.0] - 2026-10-13

### Added

- `scripts/run_project.py`: running the analyzed project now takes one choice from the user.
  - `plan` checks the machine without changing anything and writes a decision card (`run/plan.md`):
    - whether Docker is running or can be started automatically (OrbStack, Docker Desktop, Colima, systemd, dockerd);
    - registry access, download size, memory and disk against the project's documented minimums;
    - ports and same-name containers;
    - amd64-only images on ARM machines;
    - host permissions the compose file asks for (privileged, docker.sock, host directories, host network).
  - `run` does the rest after the user chooses: starts Docker, pulls only missing images, starts the stack from a copy of the code (`run/work`), waits until containers are healthy and the web page responds, screenshots the pages in `run/pages.json` (with page text for agents that can't view images), and cleans up.
  - Failures come with the reason and a plain-language tip (out of memory, port in use, `vm.max_map_count`, rate limit, network, and so on), plus saved container logs.
  - `cleanup` removes only this run's containers, networks and newly created volumes; existing named volumes and images are kept.
  - `handoff`: when the current environment can't run the project (cloud sandbox, no registry access), writes `run-locally.md` with a one-line prompt for the agent on the user's computer.
- `references/run-project.md`: card options, `pages.json` format, login, failure handling.

### Changed

- `check_env.py` ends with a one-line verdict on whether projects can be run here; it reports whether Docker can be started automatically, whether the user lacks Docker permission, and whether Docker Hub is reachable (registry mirrors are taken into account). Output is UTF-8 on Windows consoles.
- SKILL.md section 3 rewritten: the run decision card is shown with the plan at the start, so the user answers once; unattended runs stay static-only.

## [1.1.1] - 2026-10-13

### Changed

- `checklinks.py` reports placeholder references as problems: a single-line reference that points to a blank line, a bracket-only line, or a file-header line 1 (`import`, `package`, `{`, shebang). Such references show where a file is, not that the claim is true.
- SKILL.md evidence rule: a reference must point to the lines that prove the claim (definition, config entry, call site, branch); if none can be found, downgrade ✅ to 🔍 or ❓.

## [1.1.0] - 2026-10-13

### Changed

- `checklinks.py` now verifies both commit-pinned permalinks and `path:line` references (file exists at the commit, line range in bounds).
- Bare file names are resolved to their full path when unique in the repository; ambiguous names are reported.
- In GitHub projects, `path:line` references are reported as "not a permalink"; `--fix` rewrites them into permalinks.
- A numbered layer document with zero code references now fails the check instead of passing with "0 links, 0 problems".
- New hint: lines marked ✅ without a line-level code reference are listed for follow-up (does not affect the exit code).
- `checklinks.py` accepts `local` in place of `owner/repo` for local repositories.
- Skill lookup also checks `~/.workbuddy/skills`; when only SKILL.md is installed, the agent fetches the scripts by cloning this repository into `~/.cache/repo-dissect-skill`.
- SKILL.md evidence rules: full paths from the repository root, a code reference on every ✅ line, and a passing check requires exit code 0 with references in every layer document.

## [1.0.0] - 2026-10-12

### Added

- First public release of the `repo-dissect` skill.
- Layered dissection workflow: profile, business panorama & feature architecture, technical architecture, main-flow tracing, core modules, reuse assessment, selection assessment, requirement-fit matrix, multi-repo comparison.
- Evidence rules (commit-pinned permalinks, ✅ / 🔍 / ❓ markers) and safety rules for untrusted repository content.
- Standard-library-only scripts: environment check, template diagrams (JSON → SVG), permalink checker, single-file HTML report builder.
- Agent-neutral instructions and fallbacks for Codex, Claude Code, Deep Code, DeepSeek Harness and other SKILL.md-compatible agents.
- Offline Mermaid rendering in reports (pre-rendered static SVG, or the bundled Mermaid 11.6.0 library inlined).
- RAGFlow selection-assessment example.
