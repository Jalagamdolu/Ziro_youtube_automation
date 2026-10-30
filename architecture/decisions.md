# Architecture decisions log

Each entry: context → decision → why → trade-off accepted. Claude Code appends here as the build progresses.

## D-01 Orchestration: LangGraph over custom state machine / Temporal / Airflow / Prefect
The pipeline is a straight line with three human pauses and occasional jumps back. LangGraph gives durable per-thread checkpoints (PostgresSaver), `interrupt()` for human gates, per-node retry policies and replay — without running a Temporal server or bending a batch scheduler. Trade-offs accepted: checkpoints save *after* a node (crash mid-node re-runs it → all nodes idempotent + cached by input hash); no built-in crash detection (→ reaper job); fast-moving API (→ version pinned, API verified against installed version).

## D-02 LLM access: Anthropic SDK directly, no LangChain wrappers
Prompts, JSON validation (Pydantic), token counting and cost recording stay under our control; one less fast-moving dependency. LangGraph is used for orchestration only.

## D-03 One agent only (research); everything else is a workflow step
Research's path is unknowable in advance (search → fetch → verify → repeat). Script/package/storyboard have known shapes; fixed steps are cheaper, testable and predictable — which the rubric rewards (reliability, reproducibility, cost).

## D-04 State machine names from brief §05
`draft → researching → research_review → scripting → script_review → storyboarding → rendering → qa_review → approved → export_ready` (+ mock_published, metrics_stub). The brief is the contract Hemu grades against; inventing parallel names invites drift.

## D-05 Three gates, placed before money is spent
research_review before scripting (facts are cheapest to fix), script_review before any TTS/render spend, qa_review before export/publish. Gate nodes contain no side effects before `interrupt()`; every decision recorded with reviewer, notes, timestamps (opened_at → decided_at feeds manual-review minutes in the cost report).

## D-06 Publish safety in types, not convention
`Publisher` accepts only a run with an approved qa_review row; idempotency key = project_id; job id `project:stage:attempt` collapses duplicate clicks. Mock receipt mirrors a real `videos.insert` body so a future sandbox adapter is a config change.

## D-07 TTS: Sarvam primary, behind an adapter; timings from WhisperX
Brief names Sarvam for Telugu/Hindi/English and the audience is Indian students. Alignment is done ourselves (WhisperX) so subtitles/chapters never depend on a vendor's timestamp format — the TTS adapter stays swappable.

## D-08 Render: Remotion for visuals, FFmpeg for finishing
Brand-quality motion (titles, bullets synced to narration) is far easier as React templates driven by `scenes.json`; FFmpeg handles mixing, caption burn-in and loudness (~ −14 LUFS). Thumbnail rendered from the same brand system (no AI image generation — predictable, on-brand, license-clean). Check Remotion's company-size licensing before the founder review.

## D-09 Skill pack vendored, pinned, unmodified
All 11 folders at commit a2feb21 under `src/vendor/` (tools import across folders). Wrapped, never edited; MIT attribution kept. "Ship it, or change it?" endings stripped from prompts — our gates replace them. REUSE.md tracks exactly what is reused vs custom (a known founder question). Known quirks documented: retention.py arg order; English-only regexes; voice file path → `make install-voice`.

## D-10 Claim integrity is deterministic code, not LLM judgment
Every number/%/date/named result must map to an approved claim id; banned-claim scan (salaries, placements, testimonials, partnerships, certifications, metrics) blocks before any reviewer sees it. Research verifies quotes against fetched pages (httpx + trafilatura). T03's "invented claims are blocked" cannot rest on a model's self-report.

## D-11 No MCP connections in the sandbox phase
Supabase/GitHub MCP would help development, but the sandbox-isolation rule wins for now; recorded as a future option. Runtime pipeline never uses MCP — determinism, cost control and fault-injection testing require plain adapters.

## D-12 Postgres tables are the audit log; LangGraph checkpoints are not
`approvals`, `events`, `jobs`, `costs`, `sources`, `artifacts`, `asset_licenses` are query-friendly evidence for Gates D/E and the sign-off report. `approvals` shaped compatibly with Ziro's approval-contract migration for a cheap future integration — with zero connection to Ziro systems now.

## D-13 Single engineer, two halves, one contract
Dolender builds both halves; `content_package.json` (versioned, Pydantic) remains the reviewed boundary between content and execution so each half tests independently against fixtures and the Gate B / Gate C demos stay separable.

## D-14 Solo-schedule risk policy
Cut from the bottom only: Shorts-from-long, Hindi/Telugu, sandbox YouTube adapter, second-topic render (script+package suffices per brief). Never cut gates, claim checking, retries or tests — they are the pass/fail definition.

## D-15 Schema additions beyond §6 (brief §07 wins on publication dates)
Brief §07 requires a publication date and citation for topical claims; §4/§6 omit it. Add nullable `published_at` to `claims.json` and `sources`. Also add implementation columns the architecture implies but does not list: surrogate `id` + `created_at` on every table; `jobs.error_message` ("fatal failure ends failed with reason"; attempt = `retry_count` + 1, so no separate attempt column); `approvals.decision_id` (unique) so a replayed gate resume cannot double-record a decision; `approvals.target_stage` (where a reject sends the run); `approvals.ai_disclosure` (yes/no + reason, qa_review only); `artifacts.stage` + `artifacts.stale` ("downstream artifacts are marked stale" on reject, §3); `publishing.idempotency_key` (unique, = project_id, D-06). Trade-off: schema slightly wider than §6; nothing in §6 removed or renamed.

## D-16 Linux containers for worker and DB-backed tests; Windows host runs only docker + make
RQ's default worker uses `os.fork` (absent on Windows), and WhisperX/Remotion/FFmpeg are simpler to pin in a Linux image. Worker, API and DB-backed tests run in Docker Compose; GitHub Actions runs on Ubuntu; the host needs only Docker Desktop, uv and make. `.gitattributes` forces LF so scripts work inside containers. Trade-off: local test runs need Docker up; `make test` is slower than bare pytest. Pure unit tests still run on the host with uv.

## D-17 LangGraph 1.2.18 API verified (langgraph-checkpoint 4.3.1, -postgres 3.2.0)
Checked against the installed package, not docs: `langgraph.types.{RetryPolicy, interrupt, Command}`; `add_node(..., retry_policy=RetryPolicy(max_attempts, initial_interval, backoff_factor, max_interval, jitter, retry_on))`; `langgraph.checkpoint.postgres.PostgresSaver.from_conn_string()` + `setup()`. Experiment confirmed: after a node raises, `invoke(None, cfg)` re-runs only that node; a pending gate appears in `get_state(cfg).interrupts`; a gate node re-executes from the top on resume (so nothing may precede `interrupt()`); `Command(goto=...)` from a gate performs the reject jump. We invoke with `durability="sync"` so each checkpoint is stored before the next node starts (crash safety, D-01).

## D-18 Phase 1 dependencies (one line each)
`langgraph`, `langgraph-checkpoint-postgres` — orchestration + durable checkpoints (D-01). `sqlalchemy`, `alembic`, `psycopg[binary]` — audit tables + migrations; psycopg 3 is also what PostgresSaver uses, so one driver. `redis`, `rq` — job queue (§7). `fastapi`, `uvicorn` — API (§2). `pydantic` — contracts (§5). `structlog` — JSON logs with bound context. `pyyaml` — reads `config.yaml`. Dev: `pytest`, `httpx` (FastAPI TestClient), `ruff`, `mypy`, `types-pyyaml`. Deferred until their phase uses them: `tenacity`, `respx`, `anthropic`, `trafilatura`.

## D-19 Zero-cost prototype mode (user decision, 2026-10-30)
The first deliverable is a CEO demo: the full pipeline runs end to end and renders a real playable MP4 with zero external API cost. `config.yaml` gets `mode: prototype | production`. In prototype mode the LLM adapter returns hand-written fixtures and research returns a fixture `claims.json` whose URLs and quotes were manually verified against the live pages; WhisperX, Remotion and FFmpeg run for real; publishing stays mocked. The app starts and runs with no `ANTHROPIC_API_KEY` or `SARVAM_API_KEY`. Production adapters exist only as interfaces until the user says "production mode"; asking for them in prototype mode is a FatalError. Phase order becomes 2P (fixtures + claim check + voice.md) → 3 (review UI) → 4P (local TTS + WhisperX + SRT/VTT + chapters) → 5 (Remotion + FFmpeg + QA) → 6P (export, receipt, cost report: $0 observed + production estimate).
Conflict with the brief, accepted for the demo and to be closed by production mode: brief §01 PASS needs "a reviewer enters a different topic" and lists "hard-coded scripts" as FAIL. In prototype mode only topics with a fixture can run; any other topic fails at `researching` with a clear "no fixture for this topic in prototype mode" error rather than producing fake content. Also: `hookscore.py` rewards 9–24-word hooks, while brief §07 limits a Short's hook to 0–3 s (≤7 words at 150 wpm); we keep the brief's limit, so Short hooks score in hookscore's WEAK/WORKABLE band.

## D-20 Per-claim review is part of the research_review decision
Brief §05/§07 and ARCHITECTURE §8: the reviewer approves, edits or removes each claim, and scripts may only use approved claims. The research_review decision carries `removed_claims` (ids) and `edited_claims` (id → new wording); they are stored in a new `approvals.claim_edits` JSON column (migration 0002). Scripting derives the approved set from `claims.json` plus the latest research_review approval; it never sees removed claims.

## D-21 Decisions on the Phase 2P flags (Dolender, 2026-10-30)
- Pass/fail conflict in D-19 accepted: the prototype demonstrates the flow; production mode closes topic generalisation.
- Short hooks: the brief's 3-second rule (§07) wins over `hookscore.py`'s 9–24-word preference, so the best Short hook scoring 54 (WEAK) is accepted.
- TTS: edge-tts is dropped — it calls Microsoft's online read-aloud service unofficially and without a license (brief §11 "use licensed TTS"). Before Phase 4P, Piper and Kokoro are evaluated for Indian-English voices; the winner is recorded as its own D-entry and its license in `asset_licenses`.
- Known gap: prototype fixtures exist only for the Short preset. Long (`make demo-long`) and second-topic (`make second-topic`) fixtures are deliberately not built; after the CEO demo Dolender decides between a long prototype fixture and going straight to production mode. Until then Gate B's "two script packages" is not met in prototype mode.
