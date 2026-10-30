# CLAUDE.md — Ziro YouTube Automation Engine (sandbox POC, production-grade code)

Prompt-to-video pipeline: one content brief in → researched, fact-checked, scripted, branded, rendered YouTube video out, with three human approval gates and MOCKED publishing.

## Sources of truth (precedence on conflict: brief > architecture > session prompt — and tell the user)
- `docs/BRIEF.md` — requirements. The user is **Dolender** (nickname Dolu), sole implementation engineer; **Hemu** is lead and reviewer at all three gates.
- `architecture/ARCHITECTURE.md` — design, ALREADY DECIDED. Implement it; do not redesign. Section refs below (§n) point there.
- `architecture/decisions.md` — D-01..D-14 reasoning. Any deviation → new numbered entry (D-15, …) AND tell the user before proceeding.
- `architecture/REUSE.md` — every vendored file used and where; what is custom. Keep current.
- Folder layout is fixed (§12). Implement into it; never restructure, rename or relocate.
- Do not invent requirements. If the brief is unclear, ask.

## Hard rules
- **Sandbox only.** Never touch Ziro production Supabase, the Content Studio or any real YouTube channel. No MCP server connections (D-11), even if the session has them attached.
- **Publishing is mocked.** `Publisher` accepts only a run with an approved `qa_review` row — enforced in code/types, not convention (D-06). Never publish from draft/failed/rejected/unapproved.
- **No invented facts.** No salaries, placements, earnings, testimonials, student identities, partnerships, certifications, reach or metrics unless supplied as approved facts. Every material claim maps to an approved claim-ledger entry. Claim check + banned-claim scan are deterministic code, not LLM judgment (D-10). Topical claims carry publication date + citation (brief §07).
- **Secrets** only via env vars; `.env.example` lists names only. Nothing sensitive in code, logs, screenshots, tickets (T12).
- **Brand:** written "Ziro", spoken "ZAIRO" (TTS pronunciation dict). Supplied brand assets only; never redraw the logo. Genuine screen captures only; no fabricated product UIs. All media in the asset-license ledger.
- **Audience/tone:** Indian students, early-career devs, career switchers; clear, credible, practical, energetic without hype.
- **Vendored skill pack** `src/vendor/youtube-agent-skill/` (pinned a2feb21, MIT): NEVER modify. Call tools by path via subprocess (folder name isn't importable). Strip "ship it, or change it?" / "ask the user" from prompts built from SKILL.md — our gates replace them. Skills read `~/.claude/youtube/voice.md`; source lives at `src/voice/voice.md`, installed by `make install-voice`. hookscore.py/title.py regexes are English-only.

## Stack (pin every version; use uv)
Python 3.12 · FastAPI + Pydantic v2 · LangGraph + PostgresSaver · Postgres + SQLAlchemy 2 + Alembic · Redis + RQ · tenacity · Anthropic SDK directly (no LangChain, D-02; API-billed — record every call) · httpx + trafilatura · Sarvam TTS (adapter) · WhisperX · Remotion CLI (templates/) + FFmpeg · Jinja + HTMX · structlog · pytest + respx · ruff + mypy · Docker Compose (api, worker, postgres, redis) · GitHub Actions.
LangGraph's API moves: verify the installed version's `RetryPolicy` / `interrupt` / `Command` / `PostgresSaver` before use.
Host is Windows; RQ needs `fork`, so the worker (and the DB-backed test suite) run in Linux containers / CI.

## State machine (brief §05 names, D-04) — one project = one LangGraph thread (`thread_id = project_id`)
```
draft → researching → research_review⏸ → scripting → script_review⏸ → storyboarding → rendering
      → qa_review⏸ → approved → export_ready → mock_published → metrics_stub → DONE
any stage → failed (retryable flag); gate reject → named earlier stage + required notes
```
- Only the graph changes state; nodes never route themselves. Every transition → `events` row (from, to, actor, at).
- Reject targets: script_review → researching|scripting; qa_review → storyboarding|rendering. Notes passed into the target node; downstream artifacts marked stale; upstream cached stages never re-paid.
- Graph state is small: `project_id`, `artifacts {stage: path}`, `review_notes`, loop counters, `status`. Paths, never blobs.
- Only agent: research (D-03). LLM workflow steps: draft, scripting, storyboarding, chapter-title rewrite. Everything else deterministic.

## Gates (research_review, script_review, qa_review)
- `interrupt()` with NO side effects before it; resume with `Command(resume=decision)`; reject via `Command(goto=target, update=...)`.
- Record every decision: reviewer, decision, notes, decided timestamp, opened_at, artifact_version. Reject requires target stage + notes. qa_review also requires `ai_disclosure` (yes/no + reason).
- opened_at → decided_at = manual review minutes (cost report).

## Node contract (§4)
- **Idempotent:** hash inputs; if outputs exist for that hash, reuse and spend nothing (crash mid-node re-runs it safely).
- **Outputs** to `runs/<project_id>/<stage>/` via the Storage adapter; register in `artifacts` (checksum, version, model_or_tool).
- **Costs:** every paid call → `costs` row (provider, units, unit_price from `src/config.yaml`, amount, observed_or_estimate). Snapshot config into each run.
- **content_package.json** (versioned Pydantic model) is the boundary between content half (draft→scripting) and execution half (storyboarding→export) (D-13). Each half tests against fixtures.

## Error policy
- `RetryableError` (timeout, 429, 5xx) vs `FatalError` (validation, claim check, missing input). Retry ONLY RetryableError; exponential backoff + jitter.
- Attempts: research 3 · scripting 3 · TTS 4 · render 2 · publish 5. Every attempt is a `jobs` row. Exhausted/fatal → `failed` with reason; manual retry resumes.
- Scripting claim-check revise loop max 2 → FAILED. QA failure routes back to responsible node with reason, max 2 loops.

## Execution (§7)
- API never runs the graph inline. RQ job `advance(project_id, resume_value=None)` runs to next interrupt or END.
- Job id `project_id:stage:attempt` → duplicate clicks collapse to one job.
- Workers heartbeat. Reaper (startup + every 60 s): not finished, not at a gate, no progress past per-stage deadline → log + re-enqueue `advance`.
- Postgres tables are the audit log; checkpoints are not (D-12). `approvals` shaped compatibly with Ziro's approval-contract pattern; never connect to Ziro.

## Adapters (interface + Mock each; mocks default in tests)
LLM · Search/Fetch · TTS · Aligner · Renderer · Thumbnail · Storage (local now) · Publisher (MockPublisher; sandbox YouTube OAuth = future option only).

## Testing
- Tests never call paid APIs: mock adapters + respx.
- Modules named for brief T01–T12, plus the six §08 failure simulations as fault tests (missing OAuth token, rate limit, renderer timeout, rejected script, duplicate publish click, unsourced claim).
- Graph suite: stub run end to end; worker killed mid-node → reaper resumes without re-running completed nodes; reject re-runs downstream only; publish unreachable without approval.
- Layout: `tests/{unit,graph,faults,golden,manual_qa}`.

## Engineering rules
- Type hints everywhere; `ruff` + `mypy` clean; pinned deps; Alembic migrations.
- structlog JSON; every line carries `project_id`, `stage`, `attempt`; no sensitive data.
- `src/config.yaml` holds models, prices, retries, gates, spend cap.
- Small commits (one logical step). Branch per phase; PRs map to YT-02..YT-10 (all Dolender's, Hemu reviews). Commit/push only when the user asks.
- `runs/` is git-ignored; only exported `outputs/` are committed.

## Phases — ONE at a time. After each: run all tests, report results + anything skipped/assumed, STOP for the user's "go".
1. **Skeleton + orchestration** (Gate A/D groundwork): pyproject, compose, Alembic (all §6 tables), core (models, db, errors, retry, costs, logging), full graph with stub nodes writing fake artifacts, 3 gates, retry policies, `advance` job, reaper, API (create/status/approve/reject/retry/cancel), content_package contract, Makefile targets.
2. **Content engine** (Gate B): research agent + claim ledger; scripting with hookscore.py/hooks.json (5 hooks, top 2) and title.py (10 titles, top 3); claim check + banned-claim scan; script shapes (SHORT 45–75 s hook ≤3 s; LONG 3–5 min hook+outcome ≤15 s; 150 wpm); SEO; draft chapters; voice.md with TODOs.
3. **Review UI**: Jinja + HTMX gates, run log + state timeline, download bundle.
4. **Audio**: Sarvam + pronunciation dict, WhisperX, SRT/VTT, chapters.py (00:00 first, ≥3, ≥10 s), deadair.py.
5. **Video** (Gate C): ASK for brand assets before styling. Remotion (long 1920×1080, short 1080×1920 with captions in safe areas, thumbnail 1280×720, no AI images), FFmpeg ~−14 LUFS, automated QA + qa_report + preview.
6. **Delivery** (Gate E): mock publish receipt (videos.insert shape, private, AI disclosure, idempotency key), metrics stub (reports.query shape, zeroed, source "stub"), cost report, `make export`, README, REUSE.md, asset_licenses, sign-off.md from approvals, demo script (13-min engineering demo).
Stretch only on request: Shorts-from-long, Hindi/Telugu, sandbox YouTube OAuth.

## Preset briefs (seeded; topic must stay changeable — T01)
1. SHORT "What makes an AI agent different from a chatbot?" — Indian students, English, CTA "Explore AI learning at ziro.digital".
2. LONG "Build a simple agent workflow for résumé feedback" — Python beginners; must state it is an illustrative educational build, not a real recruitment decision system.
3. SECOND TOPIC (UNTIL=script_review) "Three practical GenAI portfolio projects for freshers" — no placement/salary claims.
