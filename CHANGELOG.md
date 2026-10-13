# Changelog

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
