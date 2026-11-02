# Model quality on free tiers — evidence from the first live run

Draft for the final report. Sources: D-27, D-28, D-29 in `architecture/decisions.md`; the `jobs`, `costs` and `approvals` rows of project `87b4f951d6344cb298f30764af77779b`; the worker's `draft checked` log lines (each failed draft with its problems).

**Run:** Short, any-topic production mode, prompt *"What is RAG (retrieval-augmented generation) in AI, explained for students?"*, 2026-11-02. Reviewer at all gates: Dolender (decisions relayed from chat by Claude, recorded as such in `approvals`).

**Outcome:** research passed review on the first try. **No model-written script** passed both the deterministic checks and the reviewer's notes, so the fully automated run stopped at `failed` in scripting; that stop was the guardrails working, not a crash. The video exists only because of the human-edit bridge (D-30, below): Dolender edited a model draft by hand, the edit passed every check, and the run went on to render.

## Headline

1. **The guardrails blocked every invented outcome at $0.** Since the packaging, on-screen and narration outcome scans landed (D-28, D-29), 13 of 13 gpt-oss-120b drafts contained outcome or hype language ("accurate" ×11, "boost" ×9, "accuracy" ×6, "fix/fixes" ×7, "improve*" ×6, "hallucinations" ×3, "reliable/reliability" ×4, "prevents", "reduce", "better"), and the code rejected all of them before any reviewer saw them. None reached a gate.
2. **Before those scans, two reached the human gate** in Flash-Lite drafts that passed the original D-10 checks: the title *"How RAG Fixes AI Hallucinations"* (flagged in Claude's review notes, rejected by Dolender) and the on-screen checklist item *"Answer accurately"* (not called out by anyone; it disappeared in the next revision). Both are now blocked in code. One more gap was found in the logs, not at a gate: an outcome attached to a real citation in narration (*"…to improve answers [C1]"*), closed by D-29.
3. **Free models can satisfy countable rules, but not countable rules plus editorial intent within 2 revisions.** Neither model produced a Short of 45–75 s that also kept to the claim ledger, the reviewer's notes and the no-hype rule. The best gpt-oss draft (final cycle, draft 1) failed *only* on hype titles, even with the forbidden-word list and pass/fail examples in the prompt.
4. **Research was not the weak point.** Gemini Flash-Lite's research agent found 4 claims from IBM and AWS in 9 s and 3 calls, all quotes verified word for word against the fetched pages, none dropped; the reviewer approved all four.

## Models tried (live limits on this account)

| Model | Provider (free tier) | Used for | Observed |
|---|---|---|---|
| `gemini-2.5-flash` | Google AI Studio | — | 404 "no longer available to new users" |
| `gemini-flash-latest`, `gemini-3.8-flash` | Google AI Studio | — | 141 s and >150 s for a two-word reply: unusable |
| `gemini-flash-lite-latest` | Google AI Studio | draft, research, scripting (first) | ~1.5 s per call; good research; scripting hit its ceiling (D-28) |
| `llama-3.3-70b-versatile` | Groq | — | not offered to this account (404) |
| `openai/gpt-oss-120b` | Groq (1,000 req/day, 8,000 tokens/min) | scripting (D-28) | 0.7 s; stronger drafts; still adds hype; waits ~15–45 s per draft on the tokens/min cap |

## Failure catalogue (scripting)

20 scripting attempts in total (each up to 3 drafts; the 2-revision limit never changed): 17 failed, 3 passed checks. The 3 that passed (Flash-Lite) were then rejected by the reviewer for teaching quality.

| Failure mode | Model | Caught by | Example |
|---|---|---|---|
| Invented outcome / hype in titles, description, tags | both | packaging scan (D-28) | "How RAG Fixes AI Hallucinations", "Boost Model Accuracy with Retrieval" |
| Outcome attached to a real citation in narration | both | narration scan (D-29) | "references an authoritative knowledge base, improving the response [C2]" |
| Unsupported claim on screen | Flash-Lite | reviewer at the time; now the on-screen scan (D-28) | "Answer accurately", "Real-time external knowledge bases" |
| Screen shows words the voice never says | both | on-screen scan (D-28) | "User input" card, narration says "your query" (27 occurrences) |
| Too short (93–111 words vs 112 minimum), shrinking further on revision | Flash-Lite, gpt-oss | runtime check | 108 words after removing a duplicate sentence |
| Padding the wrong section | Flash-Lite | relevance-by-10 s check | Relevance grew past 25 words |
| Hook not among the two top-scoring hooks | both | hookscore top-2 rule | wrote new hooks, kept the old opener |
| Visual a template can't render | Flash-Lite | visual-beat check (D-28) | `flow - "User input" to "Information retrieval"` with no step list (before the parser fix) |
| Ignored "keep everything else" after a reject | gpt-oss | reviewer (fixed in code, D-28) | rewrote from scratch: it was never shown the reviewed script |
| Definition list instead of a worked example | Flash-Lite | reviewer | four claims restated in a row |
| Advice dressed as a cited claim | Flash-Lite | reviewer | "Always connect your model… [C2]" |
| Verbatim duplicate claim sentence | Flash-Lite | reviewer | C1 spoken in Relevance and again under its card |

False positives found and fixed along the way (not loosenings): filler words on screen (D-29) and a bare "may"/"march" read as a month (fixed 2026-11-02; a month is a date only with a day or year).

## Usage and time (this run, all free tier, $0 observed)

| | Calls | Input tokens | Output tokens |
|---|---|---|---|
| Gemini Flash-Lite (draft 1, research 3, scripting 25) | 29 | 109,638 | 25,459 |
| Groq gpt-oss-120b (scripting) | 18 | 80,617 | 36,783 |
| **Total LLM** | **47** | **190,255** | **62,242** |
| Tavily search | 2 credits (of 1,000/month) | | |

Groq: 18 of 1,000 daily requests. Gemini's daily cap for Flash-Lite isn't published for this account (AI Studio shows it); no daily-quota 429 occurred. Per-minute waits: Groq only, about 15–45 s between drafts, handled in place; no stage retry was caused by quotas. One attempt died when Docker Desktop restarted mid-run (connection errors), unrelated to the models.

Wall clock: draft 1.2 s · research 8.9 s · scripting 19 s across the 3 passing attempts, 686 s across the 17 failing ones (Groq attempts ~1.5–2.5 min each because of the tokens/min waits). Human review: 1 research_review (approved) and 3 script_review rounds (all rejected back to scripting).

Most of the token volume came from failed drafts: a passing Flash-Lite scripting attempt used ~4k input / 1k output tokens per call.

## How the run reached a video: the human-edit bridge (D-30)

After the last automated cycle failed, Dolender took the closest model draft and edited it by hand. That draft was gpt-oss-120b, final cycle, draft 1, whose script passed every check and whose packaging failed only on hype titles.
- **Starting point:** the gpt-oss script plus the v3 titles, thumbnail, description, tags and hooks Dolender had already approved. That combination passed every check before any edit, so the file had no failing lines, only three editorial notes for gaps the checks don't cover.
- **Dolender's edits:** the Relevance line ("…RAG stops them guessing and gives you correct answers" → "…RAG stops them guessing: it fetches the facts before it answers"); one unused hook that still said "real-time"; and three chapters instead of five.
- **Checks:** the edited package went through every scripting check, nothing skipped, with 0 automatic revisions. It passed with 0 problems. Claude then confirmed the two pre-approval conditions (Relevance speaks to the viewer and doesn't repeat C1; nothing on screen says "real-time") and relayed Dolender's chat pre-approval at script_review.
- **Trail:** `scripting/v4` holds `human_draft.txt` and `human_edit.json` (`edited_by: Dolender`); the worker logged `script human-edited Dolender`; the approval note says the script was human-edited; and no model cost was recorded for that attempt.
- **Formatting incident:** Windows 11 Notepad reformatted the first `.md` edit file on save (escaped `[`, dropped `##`, doubled line breaks). The bridge now uses `.txt`. The edit was converted back undoing only those artifacts, and Notepad's file is kept beside it as `human_draft.notepad-original.md`.
- **Render:** storyboarding 0 s, rendering 148 s (Kokoro → WhisperX → Remotion → FFmpeg). The result is 53.4 s, 1080×1920, −14.3 LUFS, 121 words in 28 caption cues, and 8 scenes of 8 types, all rendered with their content.

**What this shows:** a human editor plus deterministic checks produced a publishable-quality Short from free-tier model drafts at $0. The models contributed the research, all but one sentence of the narration (gpt-oss) and the packaging (Flash-Lite); the human contributed that one sentence, a hook and the chapters, plus the editorial judgement over three review rounds. This is not the same as the models doing it alone, and the report shouldn't present it as if it were.

## Paid comparison — not yet run

The documented upgrade is Claude through the Anthropic SDK (D-02) for draft, research and scripting, with Sarvam for Indian-English narration. The comparison run on this same brief awaits a paid key. Dolender's estimate for it is about ₹50; to be confirmed against Anthropic's and Sarvam's price pages before the run, using the per-call token counts the `costs` table already records (above). The adapters are interfaces, so the switch is configuration plus the Claude adapter, with every check unchanged.

## Conclusion

At ₹0 the pipeline is safe but not productive: the deterministic guardrails held — no invented outcome, salary, placement or unsourced figure got past them once the D-28/D-29 scans were in place — but the free models could not write a script that clears those guardrails and a reviewer's editorial notes within two revisions. With a human editor in the loop (D-30) the same pipeline did reach a checked, rendered Short at $0. The bottleneck is model quality, not the pipeline. The recommendation stands: keep the checks exactly as they are and run the Claude comparison on this brief before choosing the production model.
