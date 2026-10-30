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
| _none yet_ | | |

## Custom (not from the skill pack)

Filled in as the build progresses.
