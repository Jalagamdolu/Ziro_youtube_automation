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
Brief §07 requires a publication date and citation for topical claims; §4/§6 omit it. Add nullable `published_at` to `claims.json` and `sources`. Also add implementation columns the architecture implies but does not list: surrogate `id` + `created_at` on every table; `jobs.attempt` and `jobs.error_message` ("fatal failure ends failed with reason"); `approvals.decision_id` (unique) so a replayed gate resume cannot double-record a decision; `approvals.ai_disclosure` (yes/no + reason, qa_review only); `costs.created_at`. Trade-off: schema slightly wider than §6; nothing in §6 removed or renamed.

## D-16 Linux containers for worker and DB-backed tests; Windows host runs only docker + make
RQ's default worker uses `os.fork` (absent on Windows), and WhisperX/Remotion/FFmpeg are simpler to pin in a Linux image. Worker, API and DB-backed tests run in Docker Compose; GitHub Actions runs on Ubuntu; the host needs only Docker Desktop, uv and make. `.gitattributes` forces LF so scripts work inside containers. Trade-off: local test runs need Docker up; `make test` is slower than bare pytest. Pure unit tests still run on the host with uv.
