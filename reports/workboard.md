# Workboard

## Roles

The brief (§04) names Hemu as team lead and reviewer. Operationally this project is run by one person: **Dolender** does all engineering (YT-02..YT-10), reviews and merges every PR, and is the reviewer at all three pipeline gates (research_review, script_review, qa_review). The approvals table records Dolender as approver, and the final sign-off (`reports/sign-off.md`) is Dolender's.

## Known gaps

- Prototype mode has fixtures only for the Short preset; `make demo-long` and `make second-topic` fail with "no fixture for this topic" until long/second-topic fixtures or production mode exist (D-21). Gate B's two script packages are pending that decision.
- Phase 4P TTS engine (Piper vs Kokoro) not chosen yet (D-21).
- Demo triage (D-25): captions timed per sentence (not WhisperX), FFmpeg-only plain video, no chapters / dead-air QA yet (WhisperX, VTT, end card and `[ON SCREEN]` visuals landed in Sprint B). Voice: `af_heart` at 0.95, picked by Dolender (D-23).
- Official Ziro logo without the "#1 AI Career Intelligence Platform" tagline (or approval of that claim) is still needed from the team; until then end cards use the text wordmark (D-26).
- Remotion company license: free while evaluating; the founder must check it before commercial use (D-26).
- Sprint B (2026-11-02): all scene templates built; the demo Short is re-rendered through the real path (Kokoro af_heart at 0.95 → WhisperX → Remotion → FFmpeg; 55.5 s, −14.2 LUFS measured) and exported to `outputs/demo-short`. Awaiting Dolender's review of the video. Still open: chapters.py, deadair.py, thumbnail is plain text (no template yet), Long format templates.
- Sprint A (2026-11-02, D-27): production mode on free tiers is built and mock-tested (Gemini → Groq fallback, Tavily search + own page fetch with quote verification). The first live any-topic run waits for GEMINI_API_KEY / GROQ_API_KEY / TAVILY_API_KEY in `.env`.
- **Long format templates unbuilt; the brief's long-video deliverable is open.** Rendering supports Shorts only (D-26), so a Long run fails at rendering. Preset 3's Long run (ec09fd16, "Three practical GenAI portfolio projects") was cancelled at research_review on 2026-11-03 for this reason.

## Next UX items (logged 2026-11-03; building freeze until the two live runs finish and the review queue clears)

Why: on run 69869d1c, Claude's prepared draft (D-32) was overwritten by a submit from a page loaded before the draft was placed. That cost four failed rounds.

1. **Priority: refuse stale edit submits.** The edit form carries the checksum of the draft it was loaded with. If the stored draft has changed since then (for example a Claude-prepared draft was placed), the submit is refused with "the draft changed since you opened this page; reload", and nothing is overwritten.
2. **Draft history picker.** Keep every draft for a run instead of overwriting `last_failed_draft.txt`: the model's, Claude's prepared draft and each failed hand edit. Add a picker in the edit box to load any of them.

## v2 Content Studio (branch `v2-content-studio`, from `architecture/v2-architecture.md`)
Build order: Step 1 Claude writer + uncited-line detector + Haiku support flags + budget caps (D-42..D-45) · Step 2 Sarvam voice · Step 3 topic planner + scheduler + login · Step 4 split layout + two-layer captions + shot planner.

Status 2026-11-05: Steps 1-4 built with mocks (D-42..D-50), 169 tests green. Full mock run fbeba525 went planner → scheduler → fixture script → script gate → split-layout render (placeholder presenter, Kokoro) → QA → final gate → mock publish.

Waiting on people:
- ANTHROPIC_API_KEY: then one live scripting run to script_review (drafts needed, cost).
- SARVAM_API_KEY + voice ID (sir's clone, else a stock bulbul:v4-flash voice): then one listen test; drop the "Ziro → Zyro" spelling if Sarvam says Ziro right. Check the Sarvam price (config `sarvam-tts-characters` is an estimate).
- Sir's base clip (1–2 min, good light) + signed consent, and the GPU own/rent decision: lip-sync and FLUX start then.

Open v2 items:
- OPEN DECISION, owner sir: avatar provider for the presenter zone (HeyGen or others). The brand placeholder stays until then (D-55).
- Pick the default Ishita voice by ear (samples sent 2026-11-05); `ishita_en_stories` until then (D-52).
- Missed-review notification (v2 §10 "the reviewer is notified"): shown on the planner and run page only, nothing is sent.
- Runs stranded at the retired research_review gate (905bc1b2, f00d6ed1): cancel and restart.
- The deterministic text-pop picker chooses plain lines ("So here is the test."); the Sonnet planner should do better once the key is in.

Deferred, not in this build (logged 2026-11-05):
- LatentSync lip-sync of sir's clip (needs a GPU and sir's base clip + signed consent).
- FLUX.1 schnell topic images (needs a GPU). Pixabay photos and v1 cards stay the content visuals.
- YouTube OAuth / real publish (publishing stays mocked).
- Languages beyond English.
- Any new infrastructure (no `gpu-worker` / `render` services yet; same four compose services).
