# Changelog

## [1.0.0] - 2026-10-12

### Added

- First public release of the `repo-dissect` skill.
- Layered dissection workflow: profile, business panorama & feature architecture, technical architecture, main-flow tracing, core modules, reuse assessment, selection assessment, requirement-fit matrix, multi-repo comparison.
- Evidence rules (commit-pinned permalinks, ✅ / 🔍 / ❓ markers) and safety rules for untrusted repository content.
- Standard-library-only scripts: environment check, template diagrams (JSON → SVG), permalink checker, single-file HTML report builder.
- Agent-neutral instructions and fallbacks for Codex, Claude Code, Deep Code, DeepSeek Harness and other SKILL.md-compatible agents.
- Offline Mermaid rendering in reports (pre-rendered static SVG, or the bundled Mermaid 11.6.0 library inlined).
- RAGFlow selection-assessment example.
