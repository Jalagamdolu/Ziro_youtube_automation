# Ziro_youtube_automation

Prompt-to-video pipeline for Ziro: brief → research → script → visuals → narrated MP4, with two human approval gates (the script with its claims, and the final video) and mocked publishing. v2 (Ziro AI Content Studio, `architecture/v2-architecture.md`) adds the Claude writer, Sarvam voice, a topic planner with a scheduler, a login and a split-layout Short. Sandbox only. Design: `architecture/ARCHITECTURE.md`; decisions: `architecture/decisions.md`.

## Modes

Set in `src/config.yaml` → `mode`:

- **prototype** (default, D-19): a fixture script and claim ledger for the preset Short. Needs no API keys and costs $0.
- **production** (evaluation phase, D-27): any topic. The Gemini free tier (Groq as fallback) writes the brief's learning outcome and the script. A research agent finds sources through Tavily's free plan and keeps only quotes verified on the fetched page. Copy `.env.example` to `.env` and set `GEMINI_API_KEY` (and/or `GROQ_API_KEY`) and `TAVILY_API_KEY`. `make test-live` checks the keys with a few real requests.

**Keys upgrade quality, never block (D-46).** With `ANTHROPIC_API_KEY`, Claude writes the script, Claude Haiku flags cited lines that say more than their source and Claude Sonnet plans the on-screen text; without it the free-tier writers stand in. With `SARVAM_API_KEY`, Sarvam narrates; without it Kokoro does. Each page shows a banner for a missing key, and the API logs which engines run at startup.

Narration without a Sarvam key is local Kokoro TTS. Each scene is carried by a real stock photo from Pixabay when `PIXABAY_API_KEY` is set (Pexels optional; no AI images, no identifiable faces; you can swap any photo at qa_review, D-34), otherwise a solid brand colour. WhisperX, Remotion and FFmpeg run locally, and publishing is always mocked.

## Use it

```
docker compose up -d --build
```

Open http://localhost:8000 and log in. The two users come from `.env` (`ZIRO_ADMIN_USER` / `ZIRO_ADMIN_PASSWORD`, `ZIRO_REVIEWER_USER` / `ZIRO_REVIEWER_PASSWORD`, D-47). Every gate decision records who was logged in.

**Planner** (`/planner`, admin): add a topic with keywords, guidelines, format and a publish time (IST). Its run starts 3 hours before that time, or now with "Run now". The finished video publishes (mock) at the publish time, and only after both reviews; a review still open at that time is shown as a missed publish time, and nothing publishes.

**New video**: type a topic, pick Short or Long, set any length (Shorts 15–180 s, Long 60–600 s; the script lands within ±15%, D-35), and start the run. The run page updates by itself: at script_review check the claims (with their sources and quotes) and the script together, then approve, reject with notes, or edit the script yourself; watch the video and set the AI disclosure at qa_review. When the run finishes, the same page plays the video and offers every export file for download. All runs are listed on the home page.

**Fully synthetic (D-39).** Every video is made by the machine end to end; nothing waits on a recording.

**Split layout (D-48):** content in the top 60%, a presenter zone below (a brand placeholder until sir's lip-synced clip exists), alternating with full-screen shots for the hook, 1–2 serif-italic text pops and the end card. Two caption layers: a small two-line transcription box and a large echo phrase on the divider. One cited source page per video, and the picture changes every 2–4 s (checked in QA).

## Limitations

- **Free tiers (D-27):** quality is below paid models, and daily quotas are small and change without notice. A run that hits the daily quota on every provider stops at `failed` before rendering, with "Retry the run after the quota resets"; re-run it the next day. Google's free tier may use prompts and responses to improve its products, so never put sensitive data in a brief.
- **Paid upgrade path:** Claude (Anthropic SDK, D-02) for the LLM steps and Sarvam for Indian-English TTS stay the documented production choice. The adapters are interfaces, so switching doesn't touch the pipeline, and cost rows already record the token counts for the estimate.
- **Shorts only** for rendering so far (D-26). Long-format scripts reach `script_review` but don't render.
- **Remotion license:** free while evaluating; check the company license before commercial use (D-26).
- Chapters (`chapters.py`) and dead-air QA (`deadair.py`) aren't wired in yet.
