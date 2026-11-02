# Workboard

## Roles

The brief (§04) names Hemu as team lead and reviewer. Operationally this project is run by one person: **Dolender** does all engineering (YT-02..YT-10), reviews and merges every PR, and is the reviewer at all three pipeline gates (research_review, script_review, qa_review). The approvals table records Dolender as approver, and the final sign-off (`reports/sign-off.md`) is Dolender's.

## Known gaps

- Prototype mode has fixtures only for the Short preset; `make demo-long` and `make second-topic` fail with "no fixture for this topic" until long/second-topic fixtures or production mode exist (D-21). Gate B's two script packages are pending that decision.
- Phase 4P TTS engine (Piper vs Kokoro) not chosen yet (D-21).
- Demo triage (D-25): captions timed per sentence (not WhisperX), FFmpeg-only plain video, no chapters / dead-air QA yet (WhisperX, VTT, end card and `[ON SCREEN]` visuals landed in Sprint B). Voice `hf_alpha` is provisional (D-23) until Dolender listens to `runs/tts-eval/`.
- Official Ziro logo without the "#1 AI Career Intelligence Platform" tagline (or approval of that claim) is still needed from the team; until then end cards use the text wordmark (D-26).
- Remotion company license: free while evaluating; the founder must check it before commercial use (D-26).
- Sprint B (2026-11-02): all scene templates built; the demo Short is re-rendered through the real path (Kokoro → WhisperX → Remotion → FFmpeg, −14.3 LUFS measured) and exported to `outputs/demo-short`. Awaiting Dolender's review of the video. Still open: chapters.py, deadair.py, thumbnail is plain text (no template yet), Long format templates.
