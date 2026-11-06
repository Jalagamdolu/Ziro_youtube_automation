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

## D-22 Review UI (Phase 3)
Dependencies: `jinja2` — server-rendered gate screens (§8); `python-multipart` — FastAPI form parsing for the decision forms. `htmx` 2.0.11 is vendored as `src/app/ui/static/htmx.min.js` (0BSD license, from unpkg) so the review UI works offline; it is used only to poll the run's live timeline.
Design: the UI calls the same `app/api/actions.py` functions as the JSON API and the CLI, so validation (reject needs target + notes, qa approval needs AI disclosure, claim ids must exist) is identical everywhere. Every decision is a plain form post + redirect. Decisions resume asynchronously, so the page polls every 2 s and redirects to a fresh view whenever the run's event count changes; a gate just decided is hidden until the run moves on. Artifact files are served only if registered in `artifacts` for that project (no arbitrary paths). The reviewer name is a free-text field defaulting to "Dolender"; there is no authentication in the sandbox (single reviewer, local only).

## D-23 Prototype TTS: Kokoro-82M `hf_alpha` with a ZAIRO phoneme override (PROVISIONAL, 2026-10-30)
Evaluated before Phase 4P (D-21), on the Short fixture's narration; WAVs and numbers in `runs/tts-eval/` (git-ignored; `results.json`). Neither engine ships an Indian-English voice.
- Piper: code is now GPL-3.0 (`piper-tts` 1.8.0, piper1-gpl); its only Indian female English-capable option, `hi_IN-priyamvada`, is trained on CC BY-NC-SA data (non-commercial). Rejected.
- Kokoro-82M v1.0: Apache-2.0 weights trained only on permissive/public-domain audio; run through `kokoro-onnx` 0.6.1 (MIT, no PyTorch). Word error rate when re-transcribed by Whisper small: `hf_alpha` (Hindi female voice) with English phonemes 3.4%, 49.1 s; `hf_beta` 13.6%; either Hindi voice with Hindi phonemes ~41% (unusable); `bf_emma` (British) 2.7%; `af_heart` (American) 2.0%.
- Choice: `hf_alpha` with English (`en-us`) phonemes — the closest to the user's "female, Indian-English accent" brief while staying as intelligible as the native voices. Fallback: `bf_emma`.
- Brand: every voice read the respelling "Zairo" as "zero" (espeak gives /zˈɛɹoʊ/). The pronunciation step therefore injects phonemes, not respellings: `Ziro` → `zˈaɪɹoʊ` (ZAI-ro), and `ziro.digital` is spoken "Ziro dot digital". Re-transcription now hears "Zyro", which matches the "Zai-ro" respelling.
- Provisional until Dolender listens. Overruling is one line in `src/config.yaml` (`tts.voice` / `tts.phonemes`) and a re-run: rendering re-synthesises and re-aligns from scratch; nothing is built on hand-made timings.
- **Decided (Dolender, 2026-11-02):** after side-by-side samples of the hook and the ziro.digital CTA in `hf_alpha`, `bf_emma` and `af_heart` at speed 1.0 and 0.95 (same ZAIRO override), Dolender picked **`af_heart` (American female) at speed 0.95**. Accent goal set aside for clarity; Sarvam (Indian voices) stays the production path.
- License caveat for production integration: `kokoro-onnx` phonemises through espeak-ng, which is GPL-3.0 (loaded as a shared library via `espeakng-loader`, MIT wrapper). Fine for this sandbox; flag before shipping inside Content Studio.

## D-24 Media stack lives only in the worker image (Phase 4P)
Dependencies (group `media`): `kokoro-onnx` — local TTS (D-23); `soundfile` — read/write WAV; `whisperx` 3.8.6 — word alignment (D-07). WhisperX pins `torch~=2.8` and pulls `pyannote-audio` (diarization, unused); `torch`, `torchaudio` and `torchvision` are taken from PyTorch's CPU-only index because PyPI's Linux build adds ~2.5 GB of CUDA libraries. Only the `worker` Docker target installs the group; the API/test image and CI stay small, and unit tests use `MockTTS` / `MockAligner`. Real-engine tests are marked `media` and run with `make test-media` inside the worker image. Model files (Kokoro ONNX + voices, pinned by SHA-256; the wav2vec2 alignment model) download on first use into a `models` volume, not into the image. The directly chosen media packages are releases at least two weeks old; a global resolver cut-off was not used because it conflicts with Phase 1 pins (e.g. alembic 1.20.1).

## D-25 Demo triage for the 2026-10-30 5 pm CEO demo (Dolender's call)
Full Phase 4P could not finish before the demo, so the minimal path ships first: narration WAV + SRT + a rendered Short MP4 + export with receipt. Deviations, all temporary:
- Caption timing comes from per-sentence synthesis (each sentence is its own TTS call, so its start and end are the exact sample counts of the audio we generated), not WhisperX word alignment (D-07). Cues are ≤5 words, timed within the sentence by character share. WhisperX returns post-demo.
- The video is FFmpeg only: plain dark background, topic title, burned-in captions, narration loudness-normalised to −14 LUFS; thumbnail is plain text on the same background. Remotion templates and Ziro branding wait for supplied brand assets (Phase 5).
- Deferred and logged in `reports/workboard.md`: WhisperX alignment, VTT, chapters (chapters.py), dead-air QA (deadair.py), the 2-second end card (needs the logo), `[ON SCREEN]` visuals, full automated QA, real-engine tests.

## D-26 Visuals: Remotion templates, Ziro brand values from ziro.digital (Sprint B, 2026-10-30)
Order changed by Dolender: visuals (Sprint B) before production mode (Sprint A, deferred until budget is approved); zero external cost still applies.
- **Remotion** `4.0.536` (templates/remotion, pinned, ≥2 weeks old). License: free for individuals, companies with ≤3 employees, and anyone *evaluating* Remotion who is not yet using it commercially; larger for-profit companies need a paid company license. This sandbox is evaluation. **Before Ziro uses rendered videos commercially, the founder must check Remotion's company license** — the one future cost this choice carries.
- **Pipeline:** storyboarding parses each `[ON SCREEN: ...]` beat + its narration into a scene (prototype: deterministic; an LLM storyboard is a production option); rendering synthesises scene by scene, aligns words with WhisperX, writes SRT/VTT, renders the `Short` composition (scene templates + word-timed captions in the Shorts safe area), then FFmpeg normalises loudness. Shorts only so far.
- **Templates:** one per scene type — definition card, comparison, chat bubble, flow, quote card, checklist (+ title fallback, end card). All built (2026-11-02; Dolender: proceed with the definition card as rendered). The quote card reuses the definition card's layout and shows the source's verified quote verbatim; the chat bubble's reply is typing dots, so it never shows an answer the script does not contain; the end card holds ≥2 s (voice.md) and uses the text wordmark (logo below). Template fields come only from the `[ON SCREEN]` beat and the approved claims the scene cites. A definition card's body is the approved claim's wording and its attribution the claim's source — never other text.
- **Brand values** (extracted from https://ziro.digital/ HTML + `/assets/index-2_9_nuLk.css`, 2026-10-30):

  | Token | Value | Source |
  |---|---|---|
  | background | `#0F131A` | CSS `.dark --background: 215 28% 8%` |
  | surface | `#171D26` | CSS `.dark --card: 215 25% 12%` |
  | text | `#F8FAFC` | CSS `.dark --foreground: 210 40% 98%` |
  | muted text | `#A694B8` | CSS `.dark --muted-foreground: 270 20% 65%` |
  | primary (purple) | `#9952E0` | CSS `.dark --primary: 270 70% 60%` (readable on dark) |
  | logo purple | `#5101D4` | dominant saturated colour of the official logo PNG |
  | accent (orange) | `#FF7700` | CSS `--ws-brand: 28 100% 50%` |
  | body font | Inter | CSS `@font-face` (self-hosted on the site); bundled from `@fontsource/inter` 5.3.0, OFL-1.1 |
  | display font | Space Grotesk | CSS `@font-face` (self-hosted); bundled from `@fontsource/space-grotesk` 5.3.0, OFL-1.1 |

  Also on the site: `<meta name="theme-color" content="#111111">`; Plus Jakarta Sans is loaded only for one landing page (HTML comment), so it is not used.
- **Logo:** the site serves the official logo as `/__l5e/assets-v1/b3217b6b-0889-4ee0-9568-834aaf8956b0/ziro-digital-logo-transparent.png` (1716×451, transparent; SHA-256 `d996ab53…c837c23f`), saved as `templates/brand/ziro-digital-logo-transparent.png`. It is **not placed in videos yet**: it carries the tagline "#1 AI Career Intelligence Platform", a ranking claim the brief forbids unless supplied as an approved fact, and its black wordmark needs a light background. The end card uses the text wordmark "Ziro" in the site's fonts/colours until the team supplies a logo without the tagline (or approves the claim).

## D-27 Production mode on free tiers for the evaluation phase (Sprint A, Dolender, 2026-11-02)
Dolender asked for production mode at ₹0: a real draft, research agent and scripting on free API tiers, so any topic runs while budget for paid APIs is pending. This **deviates from D-02** (Anthropic SDK) and from CLAUDE.md's "no real LLM calls until production mode"; Dolender's instruction is that switch. `mode: prototype` stays the default; `mode: production` activates the adapters below. TTS stays local Kokoro in both modes (D-23).
- **LLM:** Gemini API free tier (`gemini-flash-latest`, the alias Google keeps pointed at the current Flash model) first, Groq free tier (`llama-3.3-70b-versatile`) as fallback. Both are called over REST with httpx, so there's no SDK dependency, and prompts, JSON parsing and token counting stay ours, as D-02 intended. Models live in `config.yaml`. Free-tier limits are per project, change without notice and aren't reliably published (AI Studio and the Groq console show the live numbers), so they aren't hard-coded.
- **Quota policy:** a per-minute 429 is waited out in place (Gemini `retryDelay` / `retry-after`, up to `rate_limit_wait_max_seconds`, 3 times), then becomes a `RetryableError` for the stage's normal retries. A *daily*-quota 429 is never retried: the stage fails over to Groq. If every provider's daily quota is gone, `QuotaExhausted` (a `FatalError`) stops the run at `failed` in the first LLM stage with "Retry the run after the quota resets", never a half-made video. Any other 4xx (bad key, unknown model) is fatal.
- **Search: Tavily free plan, not Gemini grounding.** Grounding with Google Search's terms require showing Google's Search Suggestions with each grounded result, forbid modifying grounded results or mixing other content into them, and forbid using grounding to extract or collect results for another purpose. A claim ledger rewritten into a script does all three. Tavily (1,000 free credits a month; a basic search costs 1) is used only to find candidate URLs. The pipeline then fetches each publisher's page itself (httpx + trafilatura) and verifies the quote against that text, so no claim rests on Tavily output. ToS notes for production: Tavily's terms limit use to the customer's internal business purposes and let Tavily and its AI providers train on inputs, so only topic queries are sent, never personal data.
- **Research agent (D-03):** each turn, the model returns up to 4 JSON actions (search / fetch / claim / done), for at most `research.max_turns` (8) turns, aiming for about 5 claims. Code enforces the rules: it fetches only URLs that search returned, and a claim is `verified` only if its quote (≥8 words) appears in the fetched page text after typography is normalised. `researching` drops unverified claims (D-10). The publication date comes from the page's metadata when present.
- **Draft / scripting:** draft writes the learning outcome only when the request gave none, and the topic stays exactly as entered (T01). Scripting prompts are built from `voice.md`; the vendored yt-script and yt-package `SKILL.md` (with front matter, tool blocks, "The gate" and every "ask the user" / "ship it, or change it?" line removed); hooks.json's rules and formulas; and hard rules restating `script_checks`. All existing guardrails are unchanged: claim check, banned-claim scan, hookscore top-2 opener, title.py, shapes and timing, max 2 revisions.
- **Costs:** every call records its token counts (`gemini-input/-output`, `groq-input/-output`) and searches (`tavily-search`) at unit price 0.0. Totals report $0, and the rows keep the units for a paid estimate. The spend cap stays.
- **Free tier, temporary by design:** expect lower quality than paid models, plus daily caps. Google's free tier may use prompts and responses, with human review, to improve its products, so nothing sensitive is sent. The production upgrade path stays Claude (D-02) + Sarvam TTS, behind the same adapter interfaces.
- **Dependencies:** `httpx` moves from dev to runtime for all provider and page HTTP. `trafilatura` 2.3.1 extracts a page's main text and date (named in ARCHITECTURE §2). `respx` 0.23.1 (dev) mocks HTTP so tests never call a real API; `make test-live` (ZIRO_LIVE=1) is the only path that does.

## D-28 Scripting moves to Groq `gpt-oss-120b`; Gemini Flash-Lite hit its quality ceiling (Dolender, 2026-11-02)
Evidence from the first live run (project `87b4f951…`, Short "What is RAG (retrieval-augmented generation) in AI, explained for students?"). It is recorded here for the final report's model-quality section.
- **Gemini on this free-tier account:** `gemini-2.5-flash` returns 404 ("no longer available to new users"). `gemini-flash-latest` and `gemini-3.8-flash` took 141 s and >150 s to answer a two-word prompt (thinking tokens, free-tier queueing), so they're unusable at ~10 calls per run. `gemini-flash-lite-latest` answers in ~1.5 s and became the configured model (D-27).
- **Flash-Lite was fine for research and draft:** research took 9 s and 3 calls, with 4 claims from IBM and AWS, all quote-verified and none dropped. Learning outcome: 1 call.
- **Flash-Lite hit its ceiling on scripting.** Over 10 scripting attempts (each up to 3 drafts, the max-2 revision limit unchanged), 7 failed the deterministic checks. Recurring failure modes, even with revision notes that state the exact word count to add, the section to add them to, the two allowed hooks, and its own previous draft:
  - consistently writes under the minimum length (93–111 spoken words against 112) and shrinks further when asked to fix something else;
  - pads the wrong section (Relevance instead of Example), breaking the 10 s relevance rule;
  - repeats a claim sentence verbatim in two sections;
  - copies on-screen words from reviewer notes ("Stale data") while dropping the narration that says them, so screen and voice disagree;
  - adds unsupported claims to packaging ("How RAG Fixes AI Hallucinations", "Accurate answers"), now blocked in code.
  The three drafts that passed met the checks but needed three human review rounds for teaching quality (no worked example, advice dressed as a cited claim, a "real-time" framing the reviewer had ruled out).
- **Decision:** a per-stage provider order in `config.yaml` (`llm.order`). Draft and the research agent keep Gemini Flash-Lite first, because it's fast and good enough there. Scripting goes to Groq first, with Gemini as fallback. Dolender asked for Llama 3.3 70B, but Groq no longer offers it to this account (the model list returns 404 for `llama-3.3-70b-versatile`). The strongest text model it does offer is **`openai/gpt-oss-120b`** (OpenAI open weights, Apache-2.0, 131k context). Live limits on this account: 1,000 requests/day and 8,000 tokens/minute; per-minute 429s are waited out as in D-27.
- **Unchanged:** every check and the 2-revision limit. The model was changed, not the bar.
- **Checks added during this run** (each traced to a failure above; all deterministic, D-10): visual beats a template can't render are rejected (`storyboarding.visual_problems`); titles, thumbnail, description and tags get the banned-word scan plus an outcome-word rule (fixes, hallucinations, better, accurate, …, allowed only if an approved claim uses the word); on-screen quoted text gets the same scan and may only show words the narration says, the topic, or a cited source's title (the label "example"/"illustrative" excepted). Revision notes now say exactly what to change.
- **Model-quality takeaway:** small free models can satisfy hard, countable rules only with very explicit feedback, and still miss editorial intent. The deterministic checks caught every unsupported claim in packaging and on screen; teaching quality still needed the human gate. The paid path (Claude, D-02) remains the recommendation for production.
- **Reject hand-off fixed:** after a script_review reject, scripting now gives the model the reviewed script (the newest `script.md`) together with the notes, so "keep everything else" can be followed. Before this, the model saw only the notes and rewrote from scratch.

## D-29 Outcome words are claims in narration too; filler words may appear on screen unspoken (Dolender, 2026-11-02)
Two changes to the D-10 checks, from the gpt-oss drafts in the live RAG run:
- **Narration outcome scan (closes a D-10 gap):** `claim_problems` only caught figures, dates and banned language, so a narration sentence could attach an unsupported outcome to a real citation and pass. Examples: "connects a model to an external knowledge base **to improve answers** [C1]", where C1 says "optimizing the performance", and the uncited "This makes answers current and **reliable**." The outcome-word rule from packaging now also applies to narration: improves, reliable, accurate, hallucinations, fixes, better, boost, … fail unless an approved claim uses the same word. It is a tightening, approved by Dolender.
- **Filler-word exemption (false-positive fix):** the screen-must-match-voice rule (D-28) also flagged function words, e.g. the chat bubble "When is my exam?" failed because the voice said "the exam date". A fixed list of function words (what, when, then, your, with, …) may now appear on screen unspoken. Content words still must be spoken, so a "Stale data" card still fails if the voice never says "stale".

## D-30 Human-edit bridge for scripting (Dolender, 2026-11-02)
When the free models can't produce a passing script (D-28), the reviewer can edit a package by hand and send it through the same checks. `src/app/nodes/human_edit.py` renders a package as plain text (`=== SECTION ===` headers; `!!` note lines name the rule each failing line breaks, with an example fix) and parses it back. If `<project_id>/scripting/human_draft.txt` exists, scripting uses it instead of calling the model:
- **Every check runs, none skipped:** the same claim check, banned and outcome scans, shape and timing, visual-beat, on-screen, hookscore top-2 and title.py checks. There are 0 automatic revisions, because nobody is there to revise; a failing edit stops the stage with the rule list, and the reviewer edits again and retries.
- **Trail:** the stage's artifacts include the edited file (`human_draft.txt`) and `human_edit.json` (`edited_by`, from the file's `=== EDITED BY ===` section). The log line `script human-edited` names the editor, and no model cost is recorded because no model was called. script_review still follows as normal.
- **Limitation:** the stage cache key doesn't include the file, so an edit made after scripting has *passed* needs a reject (new notes) to re-run. Editing after a failure, which is the bridge's use, always re-runs.
- **Last failed draft (2026-11-02, from run `82a703e1`):** when scripting fails its checks after every revision, the full last draft (script and package), flagged with the rules it broke, is saved as `<project_id>/scripting/last_failed_draft.txt`. The failed view offers it as "Edit the last draft myself". Before this, a run whose scripting never passed couldn't reach the bridge at all, and failed packages were lost (only their scripts were logged).

## D-31 One-page product UI (Phase 3 full, Dolender, 2026-11-02)
The D-22 review UI becomes the primary path: type a prompt, end with a playable video, never leave the browser. It is still Jinja + HTMX with no build step, and every action calls the same `app/api/actions.py` functions as the JSON API, so the approvals rows and the validation are identical. The API still never runs the graph inline.
- **Landing:** `/` shows the prompt box on first use, then the list of all runs (topic, format, state, created, recorded spend). `/new` always shows the prompt box. The header shows the current `mode`.
- **Run page:** a per-stage table (state, attempts with failures counted, time from the `jobs` rows; gates show waiting/approved/rejected) above the existing state timeline, run log and decisions. It is polled every 2 s and redirects whenever a new transition is recorded.
- **Gates:** research_review gains "Approve all N claims as-is" beside the per-claim keep/edit/remove form; script_review and qa_review are unchanged.
- **Hand edit in the browser (D-30):** at script_review, and after a failed scripting run, an "Edit the script myself" box holds the package in the bridge format. Submitting writes `human_draft.txt` and either rejects to scripting (at the gate, with a recorded note naming the editor) or retries the failed stage. Every check runs. A hand edit that fails comes back annotated with `!!` rule notes. Scripting deletes the file once it has used it (`Storage.delete`), so a later reject goes back to the model.
- **Finished run:** the video player, the thumbnail, one download button per export file (MP4, SRT, VTT, thumbnail, content package, claims, mock receipt, cost report), the ZIP bundle and a cost table by provider. Files are still served only if registered as that project's artifacts (no arbitrary paths from `runs/`); FastAPI's `FileResponse` answers Range requests, so the player can seek.
- **No authentication:** the reviewer name is a free-text field defaulting to Dolender. This is fine for a local sandbox. Authentication (and reviewer identity from the login, not a text field) must come before any deployment (README).

## D-32 Free-tier bridge: standing procedure for scripting failures (Dolender, 2026-11-02)
On free-tier models, scripting fails its checks on most topics (D-28). Until Dolender says otherwise, every run that fails at scripting after its revisions is handled like this:
1. **Claude drafts a fix.** Claude corrects the run's flagged last draft (`last_failed_draft.txt`, D-30) using **only that run's approved claims**. It fixes every flagged line and the problems the checks don't cover (hiring outcomes, earnings hints, unsupported comparisons, invented specifics). It keeps the model's draft wherever it is clean, labels examples as illustrative, and adds no new facts.
2. **Every check runs before handing it over:** the same claim, banned/outcome-word, shape and timing, visual-beat, on-screen, hookscore and title.py checks scripting runs (`_problems`), against that run's brief and approved claims. Only a draft with no problems is placed.
3. **Placed for review, never submitted by Claude:** the draft replaces `last_failed_draft.txt` (the model's draft is kept beside it as `last_failed_draft.model*.txt`), so it appears in the run's "Edit the last draft myself" box. Its first `!!` lines say Claude prepared it. Claude then tells Dolender "run <id> ready for review".
4. **Dolender submits:** he reads it in the UI and submits as "Dolender (drafted by Claude)". The trail (`human_edit.json`) records that. Checks always run again on the submitted version; nothing is bypassed, and script_review and qa_review stay his.
- **Bridge fix found while starting this:** a hand edit is now used once whether it passes or fails. Before, a failed edit kept its file, so "Retry" re-ran the same rejected text instead of going back to the model (run `1ef06ab9`: two identical "after 0 revisions" failures).
- **Scope:** this procedure covers the evaluation phase on free tiers only. It does not replace the model-quality finding (D-28): a human-plus-Claude drafting loop is not the models doing the work, and reports must say which videos went through it.

## D-33 Stock footage backgrounds: Pixabay primary, Pexels optional (Dolender, 2026-11-02)
Scenes get a moving background behind the cards: a muted stock clip under a brand tint. Pexels has paused new API keys, so **Pixabay is primary**. Pexels is an optional secondary, used only if `PEXELS_API_KEY` exists; its absence is silent and never blocks. With no key at all, scenes keep the solid brand background. It works in both modes at $0 (free APIs).
- **Adapter** (`src/app/adapters/stock.py`): `PixabayStock`, `PexelsStock`, `MockStock`. Providers come in `config.yaml` `stock.providers` order, each only if it has a key.
- **Query in code, not by a model:** `background_query` takes two content words from the topic plus "technology". If that yields fewer than `stock.clips_per_video` (3) usable clips, it falls back to "abstract technology background".
- **Filters in code:** `safesearch=true`, and every clip with `isAiGenerated` is dropped (the brief bans AI imagery; the flag is in Pixabay's responses though not in its docs). So is any clip tagged with people (person, woman, face, crowd, …) or a brand (logo, apple, google, iphone, …), and any file over 30 MB. Pexels has no tags, so its page slug is filtered instead.
- **Pixabay terms:** results must be cached for at least 24 h, there's no permanent hotlinking, no systematic mass downloads and few automated queries. So search results are cached by query hash under `runs/_stock/`, each clip is downloaded once and stored (the 720p file), and a video makes at most two searches and three downloads. Each uncached search gets a $0 `pixabay-search` cost row.
- **Render:** `rendering.backgrounds` puts clips into the Remotion public dir and assigns them round-robin to every scene except the end card. `Background.tsx` loops the clip (muted, `objectFit: cover`, 3 px blur), then a 18% logo-purple layer and a dark brand gradient so text stays readable.
- **Licenses:** one `asset_licenses` row per clip (`type stock_video`, license "Pixabay License", the clip's page URL as source, the license page as proof, plus the run and the query; migration 0005 adds `project_id` and `query`).
- **Credit:** "Stock footage: Pixabay" is appended to the mock-publish description; Pixabay's license doesn't require it, but it's courtesy.
- **QA:** `qa_report.json` → `stock` (clip count, query, provider, all clips licensed for this run, no people or brand tags, credit). If either check is false, rendering stops instead of shipping the video.

## D-34 Photo-led videos: one real photo per scene, reviewer approves each (Dolender, 2026-11-02)
Dolender wants every video explained by a few realistic images. This **supersedes D-33's tinted video backgrounds**; the adapter, the keys, the filters, the cache, the license rows and the credit stay. Decisions (Dolender):
- **Layout: photo-led, cards as captions.** Each scene is a full-frame real photograph with a slow zoom and drift (`templates/remotion/src/Photo.tsx`). The sourced cards (definition, quote, checklist, flow) sit over it at the top, and a gradient darkens only where text sits. The end card stays solid.
- **People: only when not identifiable.** Hands, backs, over-the-shoulder or far away; no faces, portraits, selfies or minors, so no photo reads as a Ziro student or testimonial (brief). Code filters tags (portrait, face, smiling, selfie, child, girl, boy, …) and brands (apple, google, chatgpt, …), and drops every `isAiGenerated` image (no AI images, brief). Tags are unreliable, so **the reviewer's look at qa_review is the real gate**.
- **Choosing: the model suggests, the reviewer approves.** Storyboarding asks the LLM for one 2–5 word photo search phrase per scene (photographable, no brands or faces; `prompts.photo_queries`). Code removes forbidden words. If the count is wrong or the phrase is empty, it builds the phrase from the scene's own words. In prototype mode the fixture supplies hand-written phrases, like its script. Rendering takes up to 4 candidates per phrase (Pixabay `image_type=photo`, vertical, `safesearch`), cached by query hash, and uses the first or the reviewer's choice.
- **Swap at qa_review:** the QA panel shows each scene's photo, its search phrase and the alternatives as Pixabay previews (temporary display of search results is allowed). "Use this photo" stores the choice (`<run>/rendering/photo_choices.json`) and rejects to rendering with a note naming the reviewer and the swap, so the video is re-rendered with it.
- **Records:** one `asset_licenses` row per photo used (`stock_photo`, "Pixabay License", page URL, run, query). "Images: Pixabay" is appended to the mock-publish description. `qa_report.stock` holds the photo count, all licensed, no faces, minors or brands, and the credit; a failure stops rendering.

## D-35 Any video length, ±15%; the Ziro logo on the end card; edit before approving (Dolender, 2026-11-03)
- **Length — overrides brief §07 at Dolender's request.** The brief fixes a Short at 45–75 s and a Long at 3–5 min. Now the reviewer asks for any target: Shorts 15–180 s, Long 60–600 s (`contracts.DURATION_LIMITS`). The script's estimated runtime at 150 wpm must land within **±15% of the target** (`script_checks.runtime`), and a miss names the word count to add or cut. The prompt's per-section word budgets scale with the target, while Hook (≤3 s), Relevance (by 10 s) and the CTA stay short. The finished video's QA `duration_ok` allows ±25%, because narration pauses add time to the estimate. The brief's other shape rules are unchanged.
- **Logo.** Dolender records **"#1 AI Career Intelligence Platform"**, the logo's tagline, as an approved fact, which lifts D-26's block. The official PNG (`templates/brand/ziro-digital-logo-transparent.png`) is used **unaltered** on every end card, on a white panel because its wordmark is black, above "ziro.digital". The asset-license row is updated (migration 0006). The claim is approved for the logo only; titles, descriptions and narration still may not say "#1" unless a claim in the run's ledger does (packaging scan, D-28).
- **Edit before approving.** At script_review the hand-edit box (D-30) now sits directly under the script, above the Approve button, so editing is offered before approval rather than after the reject form.

## D-36 A real presenter on camera (Dolender, 2026-11-03)
Dolender wants a real man or woman to explain the video. The options were a real person recording, a licensed AI avatar, or no presenter; Dolender chose **a real person records**. AI avatars would override the brief's no-AI-imagery rule and need a paid service. Animating a real person's photo without their consent is ruled out.
- **Opt-in per run:** "A person will present this video on camera" on the create form (`Brief.presenter`, default off). voice.md now says synthetic narration is the default and a real presenter is optional (it used to say "no presenter on camera").
- **Recording:** for presenter runs the run page shows the approved script as a teleprompter (narration by section, without claim markers), from script_review onwards, plus an upload box (phone video, up to 600 MB). It is stored at `<run>/recording/presenter.mp4`. If rendering starts without it, it stops with "waiting for the presenter's recording", the same failed-then-retry pattern as the hand-edit bridge (no new state, D-04). Uploading then retries the run; uploading at qa_review counts as a re-take and rejects to rendering with a note naming the uploader.
- **Render:** the presenter's own voice replaces Kokoro (no TTS cost row). WhisperX aligns the whole script to the recording as one segment, which gives word-timed captions, and each scene starts at its first spoken word. If alignment loses words, scenes fall back to their share of the words. The presenter must read the script as written.
- **Layout (Remotion `Presenter.tsx`):** the presenter fills the frame for the opening line. Scenes with a card (definition, quote, flow, checklist) split the screen: card on top, presenter in the lower half. Other scenes cut away to their stock photo (D-34) while the presenter keeps talking, and only cut-aways search for a photo. The end card keeps the logo on solid brand colour. The recording plays muted in sync across cuts, with its audio as the narration track (loudness-normalised as usual).
- **Disclosure:** the presenter and voice are real, but captions and graphics are still generated, so the reviewer sets the AI disclosure at qa_review as before.
- **Limits:** a person has to record each video, about the target length. Lip-sync is exact because it's their own take, but scene cuts follow the script's words, so ad-libs drift the captions until alignment recovers.

## D-37 The reference Short's style: big captions, fast cuts, real source pages, presenter first (Dolender, 2026-11-03)
Reference: a @learnwithshopify Short ("How to use AI to automate your content creation"). It has a real presenter to camera, a top half showing genuine screen recordings of the tools under discussion, cuts every 2–4 s, and 2–3-word bold uppercase captions mid-frame. Dolender asked for all four parts:
- **Captions:** cues of up to 3 words (`CUE_WORDS = 3`), uppercase, 96 px heavy type with a black outline, at 62% of frame height; the spoken word is Ziro orange. SRT/VTT follow the same cues.
- **Faster cuts:** `rendering.plan_shots` cuts each scene into shots of about 3.5 s at word boundaries, with looks alternating per shot. Presenter videos open on the presenter's face; card scenes go split (card over presenter) ↔ presenter punch-in (1.18×); photo scenes go photo ↔ presenter. Narrated videos alternate two camera moves on the scene's photo. The card shows on card, split and photo shots and hides on full-presenter and source-page shots. The end card is one shot.
- **Real source pages (genuine screen capture, the brief's rule):** scenes that cite a claim (definition and quote cards) open on the claim's actual source page. `rendering.captures` runs `templates/remotion/capture.mjs`, which drives the headless Chrome Remotion already ships over the DevTools protocol (Node 22's built-in WebSocket; no new dependency; Chrome's own `--screenshot` flag hangs in the container). It opens the page at 1080 px wide, hides fixed/sticky overlays (cookie banners, headers), scrolls to the claim's verbatim quote, highlights it, and screenshots 1080×3000. Results are cached per URL and quote under `runs/_captures/`. `Capture.tsx` scrolls it slowly with a "Source: <publisher>" label, full-frame in narrated videos or in the top half above the presenter. Pages that time out, block bots or render blank (under 40 KB) are skipped, and the scene keeps its card/photo. Each page shown gets an `asset_licenses` row (`source_capture`, the URL, "shown briefly with attribution"). Note: unlike the stock photos, these captures aren't licensed; showing a cited page briefly with credit is common practice, and the reviewer sees every one at qa_review.
- **Presenter by default:** the create form now has "A person will present this video on camera" ticked; the API default stays off.
- **Tests now force prototype mode** whatever the local `config.yaml` says (autouse fixture); one test had been reading the live config.

## D-38 Synthetic narration is the product; presenter off by default (Dolender, 2026-11-03)
Dolender: "The machine creates the entire video itself — that is the product." This reverses D-37's "presenter by default": the create form's "A person will present this video on camera" box is now unticked, which matches the API default (off). Default runs render with Kokoro af_heart, stock photos, cards and source captures, as before D-36. The "Record the presenter" block appears only on runs created with the box ticked, so a default run never waits for a recording. Presenter mode (D-36) stays in the code as an opt-in. Run c578374e was created with presenter on; its `brief.json` and both `content_package.json` versions were switched to `presenter: false` before storyboarding (artifact checksums updated), so it renders synthetic.

## D-39 Presenter mode removed; synthetic-only is the product (Dolender, 2026-11-03; supersedes D-36's presenter path, D-37's "presenter by default" and D-38)
Dolender tried presenter mode and removed it: "The product is: machine creates the whole video itself, always." Turning it off by default (D-38) wasn't enough; it's deleted:
- **Gone:** the "A person will present this video on camera" box on the create form, the `presenter` field on `Brief` and `CreateRequest`, the recording upload route and its "Record the presenter" teleprompter block (`_recording.html`), the presenter branch in `rendering` (`RECORDING`, `WAITING_FOR_RECORDING`, `_recorded`, `scene_times`, `set_layouts`, presenter looks in `_looks`), Remotion's `Presenter.tsx`, presenter/split shot kinds and `Capture`'s split mode, and the presenter tests. Deleted rather than kept unreferenced (KEEP IT LEAN); git history has D-36's code if it's ever wanted.
- **Old data still loads:** `Brief` ignores unknown keys, so `brief.json` and `content_package.json` files written with `"presenter": true` load as synthetic runs. An API client that still sends `presenter` gets a normal synthetic run.
- **Kept from D-37:** 3-word captions, ~3.5 s cuts (source page → photo ↔ second camera move, or card), source-page captures with the quote highlighted.
- **Guarantee (`tests/unit/test_synthetic_only.py`):** runs created through the UI or API, even ones asking for a presenter, go script_review → storyboarding → rendering → qa_review with no recording step; no upload route or presenter code remains in `rendering`.
- **In-flight runs:** 616e1fa6 ("What is Rag", 30 s) and c578374e had `presenter: true` in their briefs; both were switched to `false` (artifact checksums updated) before storyboarding. 46e8cc9c (D-37 style sample) was rendered with a presenter and stays as it is at qa_review; re-rendering it would now produce the synthetic version.

## D-40 Explainers are built on how-it-works claims; visual honesty: photos for the literal, diagrams for the abstract (Dolender, 2026-11-03)
Run 395cd279 ("What is Rag", 30 s) explained nothing and showed desks and server rooms. The research had approved four IBM overview claims (what RAG is, that it helps), and none said how it works, so the claim check let the script be no more concrete than they were. The relevance line was forced into "your portfolio". The photo prompt asked for a photo per scene, and an abstract software idea has nothing literal to photograph. Dolender approved three fixes:
- **Mechanism claims (research).** Every claim now has a `kind`: `definition` (what it is), `mechanism` (how it works: a concrete step, component or flow) or `other`. Benefits are never mechanism. The research agent sets it, and the reviewer sees it at research_review: a "mechanism" pill per claim and a count line ("1 definition · 2 mechanism · 0 other"). For **explainer topics**, research needs `MIN_MECHANISM = 2` verified mechanism claims:
  - Explainer topics match `script_checks.EXPLAINER`: "What is/are …", "How does/do … work", "Explain …".
  - The agent is told to search technical documentation for the steps, and its "done" is refused until it has them.
  - If the turns run out first, researching fails with a reason that lists what it did find, instead of passing vague claims to the gate. Retry, or reword the topic.
  - Scope: the requirement applies to explainer topics only, because list topics such as "Three practical GenAI portfolio projects" have no single mechanism. Widen `EXPLAINER` if more topics should need it.
- **On-topic script.** For explainers the package prompt adds rule 14:
  - Relevance is the problem the thing solves; no career, portfolio, job or project lines.
  - The Example explains the mechanism step by step, one step per sentence, citing the mechanism claims, and a flow visual's steps are those sentences' steps.
  - The hook is about what it is or how it works, not a side benefit.
  - The claim ledger in the prompt shows each claim's kind.
  - Enforced in code: `script_checks.mechanism_problems` fails a draft whose Example cites fewer than 2 mechanism claims (or all of them, if fewer were approved). It is part of the checks the hand edit also passes through.
- **Visual honesty: photos for the literal, diagrams for the abstract.**
  - A scene gets a stock photo only when the storyboarding model names a physical, photographable thing the scene is actually about. Stand-ins (a desk for "software", a library for "knowledge") are not allowed. Everything else answers "none".
  - Definition, quote, flow and checklist cards and the end card never get a photo (`storyboarding.DIAGRAMS`); the card is the visual.
  - Abstract scenes show their card or diagram on the brand background, opening on the cited source-page capture where there is one (D-37).
  - Code no longer guesses a photo query from a scene's words (`stock.keywords` removed). No phrase means no photo.
  - voice.md records the policy.
- Tests: `tests/unit/test_mechanism.py`, plus new research-agent and photo-policy tests.

## D-41 Secret leaked in .env.example Oct 30, revoked Nov 3, scanner added (Dolender, 2026-11-03)
- **Incident.** Two commits made in the GitHub web editor on `main` (`2f90288` "Add Gemini API Key to .env.example", `c727b84`) put a real Google AI Studio key (`AQ.…`) into `.env.example`. The repository is public. It was found on 2026-11-03 when branch merges into `main` conflicted on that file. The key was not the one in the local `.env` (compared without printing). Dolender revoked the old Gemini keys in AI Studio the same day.
- **Clean-up.** `main` was merged into `phase-2/yt-03-yt-04-content-engine` keeping the branch's names-only `.env.example`, which drops the key line, and that merge was carried up through `phase-3/yt-07-product-ui` and `phase-5b/yt-06-stock-footage`, so merging them removes the line from `main`. The key stays in `main`'s history. Revoking it makes that copy useless, so history was not rewritten; a rewrite needs a force-push to `main`.
- **Guard.** `make secret-scan` runs `git grep` over every tracked file for Google (`AIza…`, `AQ.…`), Groq (`gsk_…`), Tavily (`tvly-…`) and Anthropic (`sk-ant-…`) key shapes and fails on any match. CI runs it first, before lint and tests (`.github/workflows/ci.yml`). The only exclusion is `tests/manual_qa/source-snapshots/`: saved third-party pages kept as manual QA evidence, which carry Google's own public page keys. Verified: passes on the current tree and fails on a planted `gsk_` key.
- Rule unchanged (CLAUDE.md): secrets only in `.env` (git-ignored); `.env.example` lists names only.

## D-42 Claude writes the script; Gemini and Groq only stand in (Dolender, 2026-11-05)
v2 (`architecture/v2-architecture.md` §5): Claude does the text work, paid from API credits; the free tiers stay as fallbacks only.
- **Writer.** `scripting` uses `ClaudeChat` (`src/app/adapters/llm.py`) first: `llm.claude_model` in config.yaml, default `claude-opus-5-5`, effort `high`, `claude_max_tokens` 16000. The stage order is `scripting: [claude, groq, gemini]`. Without `ANTHROPIC_API_KEY` the order skips Claude, so the app still runs on the free tiers (and prototype mode needs no key at all).
- **Research stays as built.** The research agent, draft and storyboarding keep `default: [gemini, groq]` with Tavily. Unchanged.
- **Structured output.** The package is requested with the SDK's `messages.parse(output_format=PackageDraft)`, so the reply is schema-constrained JSON validated by Pydantic. Gemini and Groq ignore the schema argument and are validated afterwards, as before.
- **Prompt caching.** The system prompt holds only text that is the same for every brief: voice.md (brand, style), the yt-script and yt-package methods, hooks.json, and the banned/outcome word rules (moved from the per-brief hard rules 5 and 9 into a fixed `WORD_RULES` block). It carries `cache_control: ephemeral`; cache writes and reads are recorded as their own cost rows (`claude-opus-5-5-cache-write` / `-cache-read`).
- **Fallback.** Claude 429, 5xx, 529 overloaded, a `refusal` or a `max_tokens` stop is a RetryableError, and `FallbackChat` moves the rest of the stage to Groq, then Gemini. Anthropic's server-side `fallbacks` parameter was not used: the free-tier writers already are the fallback, and the parameter needs the beta endpoint.
- **Dependency.** `anthropic==1.17.0`: the official SDK (CLAUDE.md stack), pinned to the newest release older than two weeks without a major-version jump. Its parser `jiter` is held at 0.17.0 (0.18.0 is from 2026-10-23).

## D-43 Uncited-line detector: every body sentence cites a claim or says what it is (Dolender, 2026-11-05)
Run 9bde8902 passed every check with "The model generates an answer that blends its own knowledge with the retrieved facts." in its Example: a plain-language fact with no figure, so `claim_problems` (which only demands markers on digits) let it through.
- **Rule** (`script_checks.uncited_problems`, deterministic): in the body sections (`BODY`: Short → Example; Long → Context and Build) every sentence carries a `[C#]` marker unless it is a question, a labelled illustration (starts "For example", "For instance", "Imagine", "Suppose", "Say you", "Picture") or a line spoken to the viewer (starts "You", "If you", "Try", "Let's"). Hook, Relevance, Takeaway and CTA are not body sections; they keep the existing checks.
- Wired into the scripting check chain, so model drafts get it as revision notes and hand edits (D-30) pass through it too; the edit box explains the fix.
- **Sentence splitting fixed.** The old split did not break after a marker that follows the full stop ("…snippets. [C2] The combined prompt…"), so the sentence after a cited one hid inside it. `script_checks.sentences` now ends a sentence at its end mark (when space or the end follows, so "3.5" and "ziro.digital" stay whole) plus any markers after it. `claim_problems` uses it too.
- **Fixture.** With correct splitting, the hand-written chatbot/agent fixture had two unlabelled illustrations in its Example ("Ask it when your exam is…", "Give it a goal like…"). Both now start "For example, …"; no fact changed.
- The scripting prompt states the rule (hard rule 4).

## D-44 Support check by Claude Haiku: flags only (Dolender, 2026-11-05)
- **What.** After a draft passes every deterministic check, `scripting.support_flags` sends each cited sentence with the exact quotes it cites to `llm.support_model` (default `claude-haiku-5-5`) and asks one question: does the sentence say more than its quotes? Structured output (`SupportReport`), one verdict per sentence, `says_more` naming the addition.
- **Flags only.** The result is `support_flags.json` and a "Support check" table at script_review ("N of M cited lines flagged"). It never approves, never blocks and never rewrites: any failure (API down, bad reply) becomes "Not run: <reason>" and the script still reaches review. Only the budget cap (D-45) can stop the run there.
- Not run in prototype mode or without `ANTHROPIC_API_KEY`; the gate says so.
- Its calls are cost rows like any other (`claude-haiku-5-5-*`).

## D-45 Budget caps: tokens per run, spend per day (Dolender, 2026-11-05)
- `budget.max_tokens_per_run` (200,000 Claude tokens: input + output + cache) and `budget.max_usd_per_day` (USD 15, all recorded spend, all runs, per UTC day) in config.yaml. The per-video `spend_cap_usd` (5.0) stays.
- **Checked before every Claude call** (`costs.check_budget`), against the call's worst case: input guessed high from the prompt length, output at its `max_tokens`, priced at the cache-write and output rates, plus usage the stage has not recorded yet. A call that would pass either cap is refused with `BudgetExceeded` (a FatalError, never retried). The run fails at that stage with the cap named in the reason, nothing is sent and nothing is spent; Retry resumes once the cap is raised or the day rolls over.
- Prices for Opus 5.5 and Haiku 5.5 are in config.yaml (claude-api price table, 2026-10-06; cache writes at 1.25x input, Haiku cache reads at 0.1x input).
- Sarvam (Step 2) will be checked against the same daily cap.

## D-46 Keys upgrade quality, never block; Sarvam voice (Dolender, 2026-11-05)
- **Rule.** The pipeline runs end to end with whatever keys are present. `app.core.engines` decides from mode + keys and says so: logged at API startup (key names and presence only, never values) and as a banner on every page.
  - No `ANTHROPIC_API_KEY`: the free-tier writers (Groq, Gemini) write scripts; no support check, no shot-planner model.
  - No `SARVAM_API_KEY`: Kokoro narrates.
  - Prototype mode: fixture scripts (the Claude stand-in) and Kokoro, whatever keys exist.
- **Sarvam adapter** (`tts.SarvamTTS`, production mode with the key): `POST https://api.sarvam.ai/text-to-speech`, one request per sentence at 24 kHz WAV. Model, speaker (the voice ID: a stock `bulbul:v4-flash` voice until sir's clone exists), language and pace come from `config.yaml tts.sarvam`. 429, 5xx and timeouts are retried up to 4 times with backoff (CLAUDE.md: TTS 4); other 4xx fail at once. Every call is checked against the daily budget first (D-45). Characters are recorded at `sarvam-tts-characters`; that price is an ESTIMATE from the v2 doc and must be checked against sarvam.ai pricing.
- **Pronunciation.** Sarvam reads text, not phonemes, so `tts.sarvam.spelling` spells brand words as said ("Ziro" → "Zyro") in what Sarvam is sent only. Captions, the screen and the forced alignment keep the written "Ziro". It is on by default; drop the entry if the listen test says Sarvam pronounces "Ziro" right.
- **Per-beat WAVs at -14 LUFS.** Rendering synthesises one beat (scene) at a time, normalises it with FFmpeg's loudnorm to -14 LUFS and caches it under `runs/_tts/` keyed by voice settings + text. A re-render (photo swap, QA reject) never pays for speech again. The finished video is normalised again and its integrated loudness is measured in QA (pass: -15.5 to -12.5 LUFS).
- `docker-compose.yml` now passes `ANTHROPIC_API_KEY` and `SARVAM_API_KEY` into the containers (Step 1 had missed the first).
- Not yet heard: the live listen test waits for the key.

## D-47 Topic planner, scheduler, minimal login (Dolender, 2026-11-05)
- **Planner** (`/planner`, `topics` table, migration 0007): topic, keywords, guidelines, format, target seconds, publish time (entered and shown in IST, `planner.utc_offset`), status. Keywords and guidelines travel in the brief to the research agent and the writer. The admin adds topics, starts one now, or cancels a planned one.
- **Scheduler**: APScheduler (`apscheduler==3.11.3`, a dependency because v2 §3 names it) runs one job in the API process every `planner.check_seconds`:
  - It starts each planned topic's run `planner.start_hours_before` (3 h) before publish_at, through the same `create_project` path as "Run now". A topic starts once (claimed with a conditional update).
  - It publishes at publish_at, never earlier. After the final approval a planned run waits at `export_ready`: the `mock_published` node interrupts before doing anything, and the scheduler resumes it when due. The reaper leaves those runs alone.
- **Nothing publishes without both reviews.** The Publisher still refuses a run without an approved qa_review (D-06). A run still in review at publish_at keeps waiting; the planner row says "MISSED publish time · nothing published · waiting for your …" and the run page says the same in red. Approved late, it publishes straight away (mock).
- **Login**: two users from env (`ZIRO_ADMIN_USER/PASSWORD`, `ZIRO_REVIEWER_USER/PASSWORD`), no registration, no users table. The session is an HMAC-signed cookie (stdlib), signed with `ZIRO_SESSION_SECRET`; logins end on restart if it is unset. Every page and the JSON API need a session (401 for the API). Both users review gates; only the admin plans topics. **Gate decisions record the logged-in name**, whatever a form or API body says.
- Not done: email or other notification of a missed review (v2 §10 "the reviewer is notified"); the planner page and run page show it instead.

## D-48 Split-layout Short, two-layer captions, text pops, pacing QA (Dolender, 2026-11-05)
Replaces D-37's full-frame shot style (D-39's synthetic-only narration stands).
- **Two states** (`templates/remotion/src/Short.tsx`):
  - SPLIT: content in the top 60% (0–1152 px), the presenter zone below, a brand-purple divider.
  - FULL: the presenter zone full-screen for the Hook and the closing engagement question, a text pop, or the end card.
- **Presenter zone**: sir's clip once it exists (lip-sync is deferred). Until then a brand placeholder: the supplied `ziro-wordmark-only.png`, unaltered, on a light studio panel with a slow push-in. Never a drawn or generated person. Recording nothing, waiting for nothing (D-39 holds).
- **Captions, two layers.**
  - (a) A small transcription box: up to two short lines (7 words), white on black, under the top bar, the spoken word in orange. SRT/VTT use the same cues.
  - (b) The echo: the sentence's key words, large, in a dark pill straddling the divider; every third one in brand purple.
- **Text pops**: 1–2 per Short, full screen. The statement is narration words; the punch words are set in Playfair Display italic (`@fontsource/playfair-display` 5.2.8, OFL, license row added).
- **Source proof**: the cited page capture (D-37) now appears once per video, the first cited scene whose page captures.
- **Cards** draw at 85% inside the content box; each body shot alternates photo and card (or two framings of the card).
- **Pacing rule**: a visual change every 2–4 s. Shots aim under 3.6 s and cut at the nearest word end within 0.3 s. QA measures the longest hold, and over 4.25 s fails the render (`pacing` in qa_report). The closing end card is exempt; beats under 2 s are reported, not failed.
- **CTA**: the end card (D-35: official logo PNG on a white panel + ziro.digital) takes the CTA line. A sentence before it, such as an engagement question, plays on the presenter zone.
- **Long format** still has no templates (D-26).

## D-49 Shot planner: Claude Sonnet proposes, code validates (Dolender, 2026-11-05)
- In storyboarding, `llm.planner_model` (default `claude-sonnet-5-5`) gets every narration sentence with its section. It returns one echo phrase per sentence (1–4 words) and 1–2 text pops (2–9 words from one Relevance/Example/Takeaway sentence, 1–2 punch words). Structured output, `ShotPlan`.
- **Validator** (`storyboarding.valid_phrase` / `valid_pop`):
  - every word shown must be said in that sentence (the screen–voice rule, D-29);
  - the packaging scan applies (banned and outcome words);
  - pops only in body sections, never the Hook or the end card.
  - Anything that fails is replaced by the deterministic plan: echo = the sentence's three longest content words; pop = the first short body sentence (or a body sentence's first clause), its longest word as the punch.
- Shot TYPES (presenter / split card / photo / source proof / pop / end) are placed by code from the pacing rule, not by the model. The v2 doc's image prompts wait for FLUX (deferred).
- No key or prototype mode: the deterministic plan alone. Its calls are cost rows (`claude-sonnet-5-5-*`) under the same budget caps.

## D-50 Two gates: the claims are reviewed with the script (Dolender, 2026-11-05)
- research_review is retired (v2 §14: 3 gates → 2). researching goes straight to scripting.
- **script_review** now shows:
  - the claims first: kind pill, definition/mechanism count, source link, verified quote, dates;
  - then the script line by line, with the Haiku support flags (D-44) beside the lines they concern;
  - then hooks, titles and package as before.
- To change claims: reject to researching with notes. To change wording: hand-edit (D-30) or reject to scripting. Per-claim keep/edit/remove (D-20) went with the gate. Scripting still applies such edits recorded by older runs.
- **Gates now**: script_review (claims + script) and qa_review (final video, AI disclosure).
- **Stranded runs.** Runs created before this change and still waiting at research_review cannot resume, because their checkpoint points at a node that no longer exists. On 2026-11-05 that is 905bc1b2 and f00d6ed1; cancel and restart them.

## D-51 Claude runs every LLM step; Gemini and Groq keys removed (Dolender, 2026-11-05)
- Dolender removed `GEMINI_API_KEY` and `GROQ_API_KEY` from `.env`: Claude does all text work (v2 §2). Until now the draft (learning outcome), the research agent and the storyboarding photo search ran on `llm.order.default: [gemini, groq]`, which would fail every run at its first step without those keys.
- `default` is now `[claude, gemini, groq]`: Claude (`llm.claude_model`) runs those steps; Gemini and Groq stay listed only as fallbacks that are skipped while their keys are absent. Search stays on Tavily. Supersedes the D-42 note "research stays Gemini + Tavily".
- Every Claude call is checked against the budget caps (D-45); the research agent makes several calls per run, so expect research to cost more than scripting.

## D-52 Stock voice: Sarvam Ishita until sir's clone exists (Dolender, 2026-11-05)
- Sarvam has no "Ishitha"; the name is `ishita`. In `bulbul:v4-flash` it comes in 16 persona IDs (`ishita_<language>_<style>`, docs.sarvam.ai voices guide), five in English: `ishita_en_customer`, `ishita_en_medical`, `ishita_en_numbers`, `ishita_en_social`, `ishita_en_stories`. None is an edtech or explainer style.
- `tts.sarvam.speaker` is `ishita_en_stories` (closest to narration) until Dolender picks by ear. Listen samples were made in `ishita_en_stories`, `ishita_en_social` and `ishita_en_customer` (all three IDs accepted by the live API), each with an A/B of "Zyro" vs "Ziro" to decide whether the spelling map stays (D-46).

## D-53 "Certificate" is allowed when a source uses it (Dolender, 2026-11-05)
- Live run be7d0678 ("How does HTTPS keep a connection private?") failed scripting three times on one problem: the banned-claim scan matched `certif(ied|icate|ication)`, and a TLS/digital certificate is the core of how HTTPS works.
- "certificate(s)" moved from the always-banned list to the outcome-word rule: allowed only when an approved claim uses the word (here C4, C5), refused otherwise (a course certificate is still a claim). "certified" and "certification" stay banned outright. The prompt's word list says so; test in `test_uncited_and_support.py`.

## D-54 Sarvam voice controls in config (Dolender, 2026-11-05)
- `tts.sarvam` now holds the voice controls, using Sarvam's own parameter names (docs.sarvam.ai text-to-speech):
  - `pace` 1.0, all models;
  - `temperature` 0.6, expressiveness, bulbul:v3 and v4-flash only;
  - `pitch` 0.0 and `loudness` 1.0, bulbul:v2 only.
- Sarvam documents pitch and loudness as "NOT supported for bulbul:v3 or bulbul:v4-flash", so `SarvamTTS.voice()` sends each parameter only to the models that take it. On the current model (v4-flash) modulation is pace + temperature. Loudness is set per beat to -14 LUFS regardless (D-46).
- The per-beat audio cache key is speaker + the parameters actually sent + language + spelling. A changed value re-synthesises (and re-bills) only beats not yet made with it; values the model ignores (pitch on v4-flash) and the retry count do not invalidate the cache.
- The listen sample was re-made at the defaults (`ishita_en_stories`, pace 1.0, temperature 0.6), with the Zyro/Ziro A/B.

## D-55 The split-layout look is locked; avatar provider is sir's open decision (Dolender, 2026-11-05)
- Dolender approved the split-layout preview as-is. Locked as the v2 look:
  - the Remotion Short template (SPLIT/FULL states);
  - the two-layer captions (transcription box + echo pill on the divider);
  - serif-italic text pops;
  - the one source-proof capture per video;
  - the end card (official logo on a white panel, D-35).
  Changes to these need a new decision.
- **Open decision, owner: sir.** Which avatar provider fills the presenter zone (HeyGen or others; LatentSync on own GPU was the v2 doc's plan). Until he decides, the brand placeholder panel stays. No avatar work is done.

## D-56 UI theme: ziro.digital's light design language (Dolender, 2026-11-05)
- One stylesheet, `src/app/ui/static/theme.css`, replaces the inline styles in `base.html`. No frontend framework; HTMX unchanged; no behaviour changes.
- **Colours** are copied from ziro.digital's live CSS (`:root` of `assets/index-*.css`, light theme), each noted in the file:
  - primary #8C3CDD (`--primary` hsl(270 70% 55%));
  - primary buttons and highlights use the site's `--gradient-hero`, #8C3CDD → #C23CDD (`--accent`, magenta);
  - foreground, muted, border, lavender surface, shadows and the aurora glow are the site's tokens.
- **Login** follows the exam portal (`/exam-portal/login`, computed styles): a centred 28 px-radius frosted card on the #F3ECFA → #EDE3F8 → #F8F2FE gradient, with the official logo above.
- **Header**: the official logo (`templates/brand/ziro-digital-logo-transparent.png`, served unaltered at `/static/brand/`) on the left, the navigation on the right; the favicon is the site's Z icon (`ziro.digital/favicon.png`, copied to `static/favicon.png`).
- **Pages**: cards are white, 16 px radius, soft shadow; banners are amber pills; status uses green/amber/red pills. On phones, wide tables scroll sideways and form rows stack.
- Screenshots for review: `tests/manual_qa/ui-v2/` (login, planner, runs, finished run, script gate, QA gate, and phone-width login and planner).

## D-57 The presenter zone is sir's place; the logo is only on the end card (Dolender, 2026-11-05)
- In every video the presenter zone (the bottom 40% in SPLIT, the whole frame in FULL) shows the approved preview's placeholder: a deep purple gradient, a plain person silhouette (a circle and shoulders, no face) and a small "presenter — sir" label, placed above YouTube's bottom overlay so it stays readable. It is still: no motion.
- No Ziro logo or wordmark in that zone any more. The official logo appears only on the end card (D-35 unchanged), and a test pins both. `ziro-wordmark-only.png` is no longer used in videos; its license row says so (migration 0008).
- **When sir's avatar exists** it drops into this exact zone. `Presenter.tsx` already plays `presenter.clip` (an MP4 in the render's public folder) instead of the placeholder when the rendering stage passes one. Which avatar provider produces it is sir's open decision (D-55).
- Supersedes D-48's "wordmark on a light studio panel".

## D-58 Motion polish inside the locked layout (Dolender, 2026-11-05)
- **Cards** enter once per scene: fade in and rise 12 px over 250 ms, then hold still. Before, the entrance replayed at every cut within a scene. A scene clock (`motion.SceneOffset`) now gives each shot its offset into the scene. The chat bubble's typing dots no longer pulse.
- **Captions**: the spoken word in the transcription box turns Ziro orange and scales to 1.06x over 120 ms, with room around it so it never touches its neighbours (1.12x crowded long words). The echo phrase stays in the dark pill on the divider.
- **Text pops**: the statement scales in from 0.94x as its words rise; the punch words stay in serif italic; still 1–2 per Short.
- Unchanged: the source-proof capture scrolls slowly to the highlighted quote; photos keep their Ken Burns move; solid scenes and the presenter placeholder stay still.
- QA on the re-rendered HTTPS Short: longest hold 3.54 s (pacing rule met), loudness -14.1 LUFS.
- Seen in review, not fixed: the MDN source capture includes the page's own sidebar advert (Hetzner). The capture is genuine, but a third-party ad in our video is unwanted; hiding ad slots in `capture.mjs` is a follow-up.

## D-59 Source captures hide adverts, never the content (Dolender, 2026-11-05)
- **The honesty line.** Hiding adverts, cookie banners and popups is allowed: the same category as the fixed and sticky overlays already hidden (D-37). The article text, the quoted passage and its highlight are never altered. A capture with ads stripped is still genuine; a capture with edited content is not.
- **What `capture.mjs` hides.** It sets `display: none`, and does nothing else, on:
  - iframes and `<ins>` ad slots;
  - custom elements named like ads (`*-placement-*`, `*-ad-*`, `*-advert*`, `*-sponsor*`, `*-promo*`, `*-survey*`), for example MDN's `mdn-placement-sidebar`, which carried the Hetzner advert;
  - elements whose class or id is an ad, cookie, consent, newsletter, popup or modal name (including Google's `adsbygoogle`);
  - elements labelled as adverts or alert dialogs.
- **What it never touches.** The quoted passage, anything that contains it and anything inside it are skipped before any hiding. Nothing on the page is edited, removed or added; a test checks the script holds no text-editing calls.
- `rendering.CAPTURE_VERSION = 2` is part of the capture cache key, so every page is captured afresh once under the new rule. The MDN page for the HTTPS Short was re-captured: advert gone, quote highlighted as published.

## D-60 A Short is at most 60 seconds, pauses included (Dolender, 2026-11-05)
- **Product rule**: YouTube Shorts up to 60 s. The 60 s default with ±15% let scripts land at 69 s; the HTTPS Short ran 67.9 s and then 70.4 s.
  - The default target is now 52 s (±15% = 44–60 s): `DEFAULT_SECONDS`, the planner and the New-video form.
  - A Short's target may be 15–60 s (`DURATION_LIMITS`, was 15–180).
  - The script's runtime band is capped at 60 s for Shorts.
- **Pauses count.** Rendering adds 0.15 s after every sentence and 0.35 s between sections (now defined once in `script_checks` and used by both). `script_checks.video_seconds` estimates the finished length as speech at 150 wpm plus those pauses. A Short estimated over 60 s fails scripting with "cut about N spoken words". The HTTPS render calibrates this: Sarvam ran at ~146 wpm, with ~3.5 s of pauses.
- **The writer** aims for 130 words (52 s × 150 wpm) and is told never to pass `SHORT_WORD_CAP` = 140 words, which leaves ~4 s for pauses.
- **Backstop.** Rendering fails a Short whose real video runs over 60.5 s (0.5 s for encoder padding), with "Reject to scripting to cut words".
- **Fixture.** The hand-written chatbot/agent fixture estimated 62 s. It lost 9 words and no facts: "that match my résumé", "and writes the entries" (the on-screen flow's words stay spoken) and "are … actually". It is now 140 words, about 59 s.
- **The HTTPS Short (be7d0678)** stays at 70 s as a test artifact, per Dolender. Its review re-renders lift the cap in that one-off process only; pipeline runs keep it.

## D-61 No login (Dolender, 2026-11-05)
- Dolender: "we don't need any login". The studio runs on one machine for its one reviewer. D-47's login is removed: the `/login` and `/logout` routes, the login page and its styles, the signed session cookie, the two env users (`ZIRO_ADMIN_*`, `ZIRO_REVIEWER_*`, `ZIRO_SESSION_SECRET`, dropped from compose and `.env.example`) and the admin/reviewer roles.
- Every request acts as Dolender (`app/ui/auth.py`), so gate decisions still record Dolender in the approvals table, whatever a form or API body says. The planner is open to whoever opens the app.
- Before this is used anywhere but the local machine, a login must come back (the API binds to 127.0.0.1 only).

## D-62 A Short's requested length is a ceiling (Dolender, 2026-11-05)
- **Rule.** For `format=short` the requested seconds are the most the video may run. Up to 15% under is fine; over fails. A requested 40 s is delivered at 34–40 s (aiming for 36–40), never 44. Supersedes the ±15% band for Shorts (D-35) and D-60's 52 s default; a Short is still at most 60 s.
- **Script.**
  - The word budget aims at 90% of the requested length (40 s → 90 words) and stops at the length minus ~8% left for pauses (40 s → 92 words): `script_checks.word_budget`, stated in the prompt.
  - The speech band is 85–100% of the request (`runtime`).
  - The pause-aware estimate (`video_seconds`, D-60) must fit inside the request, or the draft goes back with "cut about N spoken words".
- **Render.** The voiced beats are assembled with the normal pauses (0.15 s between sentences, 0.35 s between sections). If the track still runs over the request, the pauses tighten to 0.05 / 0.12 s, cut from the same cached audio with nothing re-synthesised. QA then fails any Short longer than requested (0.1 s for the container's frame rounding), telling the reviewer to reject to scripting.
- **Default.** With a ceiling, the natural default is the product maximum: new Shorts default to 60 s (delivered 51–60 s, aiming for 135 words). The forms say "at most".
- Long videos are unchanged (±15%).

## D-63 Product view first, engineering in Technical details (Dolender, 2026-11-05)
- **Design test:** would we proudly demo this page to a paying client? No behaviour changed; only what a person sees first.
- **Run page:**
  - the topic, a six-step progress bar (Research → Script → Your review → Render → Your review → Published) with a spinner on the active step, and amber on "your review";
  - one plain status line ("Writing the script…", "Waiting for your final review", "Stopped — needs your attention" with the reason);
  - a ₹-per-video chip (`inr_per_usd` in config.yaml, approximate);
  - the video when there is one, and the review panel when it is your turn;
  - a decision bar pinned to the bottom of the screen: Approve, Edit (opens the edit panel), Send back (opens the reject panel, whose targets are named in words: "Script — rewrite it").
- **QA** reads as ticks ("✓ 39.2s · ✓ loudness · ✓ pacing · ✓ captions") on the final review and the finished video.
- **Technical details**, one collapsed section at the bottom (closed by default), holds everything else, unchanged: stages, state timeline, run log, decisions, the cost breakdown, the raw QA JSON, the artifact ZIP and Cancel. Nothing was removed: the audit trail is a brief requirement.
- **Planner and runs list** are cards with plain statuses; there are no stage names ("qa_review") anywhere in the product view. Words live in `app/ui/plain.py`.
- Screenshots of every page: `tests/manual_qa/ui-v3/`.

## D-64 The planner is one list: one row per video, Planned → Ready → Scheduled → Published (Dolender, 2026-11-05)
Supersedes the two-tab plan and D-47's "approved late, publishes at once".
- **One row per video, through its whole life.** A row is a planner topic, the video run it became, or both. A run started from New video (or before the planner) is a row too. Chips are plain words with colours:
  - Planned (with or without a time);
  - Being made, Needs your review;
  - Ready · needs a slot, Scheduled · time;
  - Published;
  - Missed (red), Stopped, Cancelled.
- **Order.** Ready videos without a slot (and videos whose slot was missed) are pinned at the top as "Needs a slot". Then "Coming up" by publish time, "No time yet", "Published" (newest first), and stopped or cancelled last. Home (`/`) is the planner; the old runs list is gone.
- **Add a video**: topic, guidelines, format, duration (at most) and an optional publish time. With a time, making starts 3 h before it. Without one, the row waits as Planned until you press "Make now".
- **A finished video publishes only in its slot.**
  - The final approval no longer publishes at once: the video becomes Ready and waits at export_ready.
  - You set, change or clear its publish time inline, on the row or on its page. It fires at that minute (mock now, real later).
  - Only `scheduler.publish_due` fires a slot: the slot has come and the final approval was before it. It marks the row as firing; the graph's publish step waits until it sees that mark, so retries and restarts cannot publish early.
- **Publish lock unchanged**: no final approval, no scheduling (`scheduler.schedule` refuses), and the Publisher still needs the approved qa_review (D-06).
- **Missed**: a review still open at the slot shows "Missed" in red and waits. Approved after its slot, the video never publishes on the old time; it shows "Missed · needs a new time" until it is given one.
- **Uploads** ("Upload a video", e.g. sir's recordings): an MP4 (checked by its header, at most 500 MB) becomes a Ready row. The upload records a manual final approval by the reviewer, with the AI disclosure "not synthetic — human content: uploaded recording", and an asset-license row (Ziro's own recording). It gets the same slots; at its minute the scheduler publishes it through the same Publisher lock, with no pipeline run.
- **Detail view** (click a row): topic, progress, the video player, the slot controls, the approvals in plain words, the script, and the next action. Technical details stay collapsed.
- Migration 0009: a row's publish time is optional, and a row has a kind (generated | upload).
- Screenshots: `tests/manual_qa/ui-planner/`.

## D-65 Planner final design: reshaped, not rebuilt (Dolender, 2026-11-05)
- The planner final design (one list, date-time slots, mock publish; real YouTube parked until sir's OK) is D-64 with these additions:
  - **Ready, Scheduled and Published rows** show the video's real length (from its QA report) and its cost in rupees. A Published row reads "Published (mock)" and links its publish receipt.
  - **A planned row has its own page** (`/planner/<id>`): topic, guidelines, format, length, publish time and one next action (Make now, or Cancel). Once its video exists, the row opens that video's page.
- **Safety, now tested explicitly:**
  - the schedule control is not offered on the row or the video page until the final approval;
  - a slot reached before the final approval shows "Missed" and never publishes;
  - firing is idempotent. A slot fires once (`publish_due` marks the row as firing; a second call finds nothing). A worker that dies after the mock publish but before the step is saved is restarted by the reaper, and the publish still happens exactly once (MockPublisher is idempotent on the video).
- Screenshots: `tests/manual_qa/ui-planner/` (list, phone, and the Planned, Ready, Scheduled and Published row pages).

## D-66 Planner row lifecycle: one chip, that state's actions only; Published only once confirmed (Dolender, 2026-11-05)
- **Each row shows one state chip and only the actions of that state:**
  - Planned → Make now / Cancel.
  - Needs your review → Approve / Reject, on the row. Script review: "Read script" + Approve. Final review: "Watch" + Approve, which opens the required AI disclosure (yes/no + reason). Reject opens a panel: send back to (the gate's allowed targets) + what must change (required).
  - Ready · needs a slot → Schedule (date-time picker, IST).
  - Scheduled → chip with the time and a countdown ("in 3 days", "in 26 h", "in 12 min"); Reschedule / Unschedule.
  - Publishing… → spinner, no buttons. Shown while the slot is firing, while the publish step runs, and for a finished run with no publish receipt on record.
  - Published → only after confirmation (below), with the publish time and the receipt link.
  - Failed → red chip, the reason in plain words (the step and the first line of the failed job's error), Retry. Missed (red) → Approve / Reject while the review is open, a new slot once approved.
  - Being made, Cancelled → no buttons; the title opens the video's page.
- **One approval system, two doorways.** The planner's Approve and Reject post to the same gate endpoint as the video page (`/ui/projects/<id>/decide`), with `back=/planner`. The same validation applies (reject needs a target and notes; final approval needs the AI disclosure), the same approvals row is written, and errors come back to the planner. Only `/planner` is accepted as a return address. After a decision the row says "Working on your decision…" with no buttons until the worker moves on. Retry works the same way.
- **Published is never shown on send alone.** `planner.confirmation(receipt)` decides:
  - Mock (now): the publish receipt artifact exists → "Published (mock)" + time + receipt link.
  - Real YouTube (later, after sir's OK): the receipt must carry `confirmed_at` and `watch_url`, written only after an API read-back shows the video live → "Live on YouTube" + watch link + confirmed time. A receipt without them stays "Publishing…".
- Tests (`tests/graph/test_planner.py`): chip-per-state with only that state's buttons, both approvals from the planner recorded as Dolender's with the disclosure; reject from the planner refused without a note; Publishing… (no buttons, no "Published") while the publish step has not confirmed, "Published (mock)" only once the receipt exists, back to Publishing… if the receipt is not on record; a failed run shows its reason in red and retries back to the planner.
- Screenshots: `tests/manual_qa/ui-lifecycle/` (planner, phone, Reject panel open).

## D-67 The one real YouTube target is @Ziro.Digital, and sir's consent login is the sign-off (Dolender, 2026-11-06)
Amends the CLAUDE.md "sandbox only, never touch any real YouTube channel" rule for exactly one channel.
- **The consent login is the founder sign-off.** The credential can only exist if sir personally logs in to @Ziro.Digital's Google account and grants consent. That act is the sign-off the sandbox rule required. Until that login happens, nothing is connected.
- **One-time authorization**, `make youtube-auth`:
  - It runs on the host, using only the Python standard library, because Google's redirect goes to 127.0.0.1.
  - It reads `YT_CLIENT_ID` / `YT_CLIENT_SECRET` (a Desktop app OAuth client) from `.env`, and refuses an API key (`AIza…`).
  - It prints the consent URL and catches the redirect (PKCE, state checked). It saves `YT_REFRESH_TOKEN` to `.env`, never printed or logged.
- **Scopes: youtube.upload + youtube.readonly.** Pinning the channel and checking it on every publish needs to read the authorized account's own channel (`channels.list mine=true`), which upload alone cannot do. Readonly cannot change or delete anything.
- **Pinned by ID.** `src/config.yaml` `youtube.channel_handle: "@Ziro.Digital"` is the only allowed target. After consent:
  - the account must have exactly one channel, and its handle must match;
  - then its channel ID is written to `youtube.channel_id`;
  - for any other channel, the token is revoked at once and nothing is saved.
  - `youtube_auth.matches()` is the check the future adapter repeats before every publish (handle and pinned ID).
- **Still mock.** Uploads will be private only. Public release follows the planner rules: final approval, then the slot. Publishing remains MockPublisher until Dolender switches it. No publish adapter was built here.

## D-68 PLANNED, not built: multi-platform publishing (YouTube, then Instagram Reels) (Dolender, 2026-11-06)
Roadmap only. Nothing below is implemented; publishing stays MockPublisher until Dolender switches it.
- **One publisher interface, three providers: `mock | youtube | instagram`.** This refactors today's single Publisher (D-06). Every provider keeps the same lock:
  - it only accepts a run with an approved qa_review;
  - it carries an idempotency key, so a slot fires once;
  - "Published" shows only after the provider confirms (D-66).
- **Planner: same rows, a slot per platform.** A video can be scheduled separately on each platform (e.g. YouTube Fri 18:00, Instagram Sat 10:00). Each platform gets its own chip and actions on the same row, and its own receipt. The final approval covers the video; each platform slot is a separate scheduled publish.
- **YouTube provider (first).** It uses the D-67 credential and only @Ziro.Digital, with the channel ID checked before every publish.
  - Uploads are private, with `publishAt` set to the slot.
  - It is confirmed by a read-back before the row says "Live on YouTube".
  - It must be built and proven end to end before Instagram starts.
- **Instagram Reels provider (second)**, via the Instagram Graph API: create a media container (`media_type=REELS`, `video_url`, caption), wait for the container to finish processing, then `media_publish`; it is confirmed by a read-back of the published media.
  - Needs, all external and set up by a human:
    - an Instagram Business or Creator account linked to a Facebook Page;
    - a Meta app with `instagram_content_publish` (plus the basic Instagram/Page read permissions that publishing requires) and its review;
    - a long-lived token, stored in `.env` only.
  - Same consent-is-sign-off rule as D-67: the account is pinned by ID in config, and only that account is allowed.
- **Public-URL staging for the MP4.** The Graph API fetches the video from a public URL. Plan: upload to a Supabase storage bucket and give Instagram a short-lived signed link (minutes), deleted after the publish is confirmed.
  - The bucket lives in a **separate, non-production Supabase project**. CLAUDE.md still forbids Ziro's production Supabase; using it would need its own sign-off entry.
  - Adds a Storage-style "stage" adapter with a mock for tests.
- **Build order:** (1) YouTube adapter, proven on @Ziro.Digital with private uploads; (2) publisher refactor to per-platform providers and per-platform planner slots; (3) Instagram Reels with staging.
- New dependencies for each step get their own one-line justification when they are built.

## D-69 UI and workflow final: New Video · Library · Planner; Publish now; real YouTube behind publish.mode (Dolender, 2026-11-06)
Reshapes D-64 to D-66; nothing was rebuilt from scratch. Design bar: simple, neat, phone-first.
- **Three places**: a sidebar on a desktop, a bottom tab bar on a phone. A "Needs you · N" badge counts videos waiting for a review, and those cards are pinned to the top of the Library. All times are IST.
- **One status per video, in plain words**:
  - Writing script → Needs your review (script) → Generating → Needs your review (video) → Ready → Scheduled → Publishing → Published;
  - plus Failed (the reason and Retry) and Cancelled.
  - `planner.state()` is the only place this is decided. The Library card, the Planner and the video page all show the same chip.
- **New Video**: prompt (required), keywords and guidelines (optional), and a length picker of 30/40/50/60 s. 60 s is the ceiling (D-62), and the server refuses anything else. Shorts 9:16 only: the format field is gone until long templates exist. After submit, the page shows "Researching & writing…" until the script review.
- **Script review**: beat by beat. Each fact line has its source quote, link, date and kind (definition/mechanism, D-40) beside it, and the fact checker's flags (D-44) sit on the line they concern.
  - Approve · Edit (every check runs again, D-30) · Regenerate.
  - Regenerate is a reject to scripting with optional notes; empty notes are recorded as "Regenerate the script (no notes given)." so the reject-needs-notes rule holds.
  - Research rejects stay under "Send it back". The approved script stays locked (editing is only possible at script_review or after a failed scripting run).
- **Generating**: live steps Voice → Captions → Render → Quality check. The render step writes its current step to `rendering/progress.json`, which is not an artifact. The presenter note reads "sir's avatar zone — placeholder until connected".
- **Final review**: the player, Approve (with the AI disclosure, required) and Reject (notes, back to a named stage). Approving lands the video in the Library with a "Saved to Library" toast.
- **Library**: every video as a card with:
  - thumbnail, title, real duration, IST created date, ₹ cost chip and one status chip;
  - filters All · Needs you · Ready · Scheduled · Published · Failed;
  - actions for its state only. Review now; Publish now and Schedule (Ready); Reschedule, Unschedule and Publish early (Scheduled); Retry (Failed). Preview, Download and Edit (title, description, hashtags) sit as quiet links.
  - Edits are allowed only before the upload. Each edit is a versioned `metadata.json` artifact and an audit row; the publish step uses the latest one.
  - The D-66 approve/reject buttons on planner rows are replaced by "Review now", which opens the review screen, so the final video is watched before approval. There is still one approval system (the same gate endpoint and approvals rows).
  - "Upload a finished video" (D-64) moved here.
- **Planner**: month calendar and list of everything with a time: scheduled, publishing, published, planned topics, and failed publishes with Retry. Reschedule, Unschedule and Publish early work inline. A banner says new Google API projects upload as private until YouTube's audit. "Plan a topic for later" (D-47) stays, collapsed.
- **Publish now** is a slot at this minute, fired at once through the same scheduler path and lock.
- **Publisher interface, `publish.mode: mock | youtube`.** Mock is the default and the committed value; Dolender flips it. The publish step keeps its brief state name (mock_published) and uses the configured provider.
  - **Mock** fires at the slot and is confirmed by its receipt (D-66).
  - **YouTube** (`app/adapters/youtube.py`) uses only the OAuth refresh token from .env, never an API key. A missing token is a FatalError, the §08 "missing OAuth token" failure.
    - The pinned channel (D-67) is checked before every call that changes a video.
    - Uploads are always private. A slotted video uploads as soon as it is scheduled, with `status.publishAt` = the slot, so YouTube releases it even if this machine is off. Reschedule, unschedule and publish early change that uploaded video (`videos.update`, keeping its other status fields).
    - Every upload carries `containsSyntheticMedia` and the AI disclosure in its description. A pipeline video is always synthetic (AI narration); an uploaded recording follows its recorded human-content disclosure.
    - Timeouts, 429 and 5xx are retried; any other refusal is fatal and shown with YouTube's reason.
- **Never twice.** The `publishing` row (the publish log; idempotency key = the video) is committed before any byte goes to YouTube, and every upload is tagged with a hash of that key. A retry after a crash mid-upload finds the tagged video on the channel instead of uploading again. The mock stays idempotent as before.
- **Published only after a read-back.** Every minute the scheduler reads back YouTube videos that should be live. "Published" (with link, time and video ID) shows only when YouTube says public, or when the slot has passed and processing has finished. In the second case the chip reads "Published · private": an unaudited API project keeps uploads private.
- **Data**: no drafted videos/schedules/publish_log tables existed, so they map onto what was there:
  - videos = `projects`;
  - schedules = `topics.publish_at` and `publishing.scheduled_at`;
  - publish log = `publishing`, which gains `confirmed_at` and `watch_url` (migration 0010);
  - audit trail = `events`, which gains `note`. Every action that is not a state change (schedule, unschedule, publish now, publish early, metadata edit, read-back confirmation) is a row with who, when and what. Gate counting ignores these rows.
- **Kept from the architecture, against the session prompt:**
  - Publish attempts stay at 5 (ARCHITECTURE.md §4), not 3 retries. **Confirmed by Dolender, 2026-11-06.**
  - The scheduler stays in the API process (v2 §2), not a separate worker. Its state is Postgres, it checks every minute, and it survives restarts.
- **Tests**:
  - `tests/graph/test_planner.py`: chip-per-state and actions, needs-you pin and badge, filters, toast, Regenerate, New Video limits, publish lock, Publish now, scheduling, missed slots, metadata edits, audit rows, idempotent firing, published-only-after-confirmation.
  - `tests/graph/test_youtube_publish.py` (respx, never calls Google): private with publishAt, synthetic flag and disclosure, no API key, read-back confirmation, publish now, reschedule/unschedule in place, missing OAuth token, wrong channel, crash mid-upload never uploads twice, no publish without the final approval.
- Screenshots: `tests/manual_qa/ui-v4/` (all five screens, desktop and phone).
- **Polish round** (from the ui-v4 screenshot review, 2026-11-06):
  - **Action bar**: the script review's Approve · Edit · Regenerate bar is docked to the viewport's bottom edge (above the tab bar on a phone), and the page leaves room under the script, so no beat is ever behind it.
  - **Three actions**: script review has exactly Approve · Edit · Regenerate.
    - "Reject — send it back" is merged into Regenerate (notes optional), which has a "Find new sources first" tick box: a reject to research.
    - The final review keeps Approve / Reject.
  - **Sources line**: plain words, "N sources — every fact line verified", or the flag count. The definition/mechanism breakdown (D-40) and the fact checker's status move under Technical details, and quote cards lose their category tag.
  - **Phones**: every page leaves the tab bar's height (plus the safe area) free at the bottom. The screenshot tool now sizes the window to the whole page, so fixed bars appear where a reader sees them.
  - **Thumbnail**: a missing or unreadable thumbnail (stub renders) shows a neutral "No thumbnail image yet" box.
  - **Demo data**: the screenshot builder gives each demo video a title, tags and description matching its own topic. Prototype mode's own fixture always matched its topic; the mismatch was demo-only.
