# Changelog

## [1.2.1] - 2026-10-13

Fixes from a real run in an agent with a file sandbox (WorkBuddy on macOS, Dify).

### Fixed

- Registry reachability is now checked by the Docker daemon itself (Engine API \`/distribution/<image>/json\` over the local socket) instead of from the agent's process. The daemon may use a different network path — OrbStack follows the macOS system proxy — so the old check could report "registry unreachable" while Docker could pull fine. On a Mac where Docker really can't reach the registry, the card now suggests starting the proxy and restarting OrbStack (or \`orb config set network_proxy\`) and recommends re-checking rather than handing off.
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
