# Reuse ledger: vendored youtube-agent-skill

| Field | Value |
|---|---|
| Upstream | https://github.com/Jakeschincariol/youtube-agent-skill |
| Pinned commit | `a2feb2104981a375ffd4f87ee04f4f5344ac43c6` (2026-09-16, "The YouTube agent skill: eleven skills, six tools") |
| Location | `src/vendor/youtube-agent-skill/` — exported with `git archive a2feb21`, byte-identical to upstream, no `.git` |
| License | MIT, Copyright (c) 2026 Jake Schincariol — `src/vendor/youtube-agent-skill/LICENSE` kept unmodified |
| Rule | Never edit vendored files; wrap them (subprocess by path). Update only by re-exporting a new pinned commit. |

Audit at vendoring (2026-10-30): the six Python tools use only the standard library (json, os, re, sys, csv, statistics); no network, subprocess, eval or exec. `chapters.py` and `retention.py` import `yt-edit/deadair.py` via `sys.path`, so all 11 skill folders stay together.

## Used files

Filled in as each phase wires a vendored file into the pipeline (file → where used → how).

| Vendored file | Used by | How |
|---|---|---|
| `skills/yt-script/hookscore.py` | `src/app/nodes/skills.py` → `scripting` | Subprocess `--json` on the 5 hooks; verdict, band and formula recorded per hook; top 2 kept (`hook_scores.json`, `content_package.json`). |
| `skills/yt-script/hooks.json` | read by `hookscore.py`; `src/app/adapters/prompts.py` | The 21 formulas `hookscore.py` classifies against. In production mode (D-27) its rules and each formula's name and shape also go into the scripting prompt (read only). |
| `skills/yt-package/title.py` | `src/app/nodes/skills.py` → `scripting` | Subprocess `--json --thumb` on the 10 titles; top 3 kept; a title that repeats the thumbnail text fails the stage (`title_lint.json`). |
| `skills/yt-script/SKILL.md` | `src/app/nodes/script_checks.py` (rules, not text) | Its rules are enforced as code: five hooks scored and two kept, an `[ON SCREEN: ...]` visual in every section, 150 wpm runtime, one CTA. In production mode (D-27) `src/app/adapters/prompts.py` reads its text into the scripting prompt, minus front matter, tool-usage blocks, "The gate" and every "ask the user" / "ship it, or change it?" line. |
| `skills/yt-package/SKILL.md` | `src/app/adapters/prompts.py` (production mode, D-27) | Same treatment as yt-script: its packaging rules (ten titles, a thumbnail of three words at most, no repetition) go into the prompt, and `title.py` still lints the result. |
| `templates/voice.md` | `src/voice/voice.md` | Section structure copied (MIT, attributed in the file) and filled from the brief, with TODOs for Dolender. |

## Custom (not from the skill pack)

| Part | File | Why custom |
|---|---|---|
| Claim traceability + banned-claim scan | `src/app/nodes/script_checks.py` | The pack says "never invent a number" as an instruction; D-10 needs it enforced as code. |
| Script shape (brief §07 timings) | `src/app/nodes/script_checks.py` | The pack has no notion of the brief's Short/Long section timings. |
| Claim ledger + per-claim review | `src/app/nodes/researching.py`, research_review gate | The pack's yt-viral researches angles, not citable claims with verified quotes. |
| Fixture LLM + research (prototype mode) | `src/app/adapters/llm.py`, `research.py`, `fixtures/` | D-19: $0 demo. |
| Free-tier LLM adapters, research agent, search + fetch (production mode) | `src/app/adapters/llm.py`, `research.py`, `search.py`, `prompts.py` | D-27: the pack has no API client, agent loop or quote verification. |
| Claude writer (v2) | `src/app/adapters/llm.py` (`ClaudeChat`), `prompts.py` | D-42: the pack's SKILL.md and hooks.json text goes into Claude's cached system prompt, read only, as it did for the free tiers. |
| Uncited-line detector | `src/app/nodes/script_checks.py` (`uncited_problems`) | D-43: the pack has no notion of a claim ledger. |
| Support check (Claude Haiku, flags only) | `src/app/nodes/scripting.py` (`support_flags`), `prompts.py` | D-44. |
| Budget caps | `src/app/core/costs.py` (`check_budget`) | D-45. |
