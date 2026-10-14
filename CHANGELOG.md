# Changelog

English · [简体中文](CHANGELOG.zh-CN.md)

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
