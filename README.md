# Ziro_youtube_automation

Prompt-to-video pipeline for Ziro: brief → research → script → visuals → narrated MP4, with three human approval gates and mocked publishing. Sandbox only. Design: `architecture/ARCHITECTURE.md`; decisions: `architecture/decisions.md`.

## Modes

Set in `src/config.yaml` → `mode`:

- **prototype** (default, D-19): a fixture script and claim ledger for the preset Short. Needs no API keys and costs $0.
- **production** (evaluation phase, D-27): any topic. The Gemini free tier (Groq as fallback) writes the brief's learning outcome and the script. A research agent finds sources through Tavily's free plan and keeps only quotes verified on the fetched page. Copy `.env.example` to `.env` and set `GEMINI_API_KEY` (and/or `GROQ_API_KEY`) and `TAVILY_API_KEY`. `make test-live` checks the keys with a few real requests.

Narration is local Kokoro TTS in both modes. Each scene is carried by a real stock photo from Pixabay when `PIXABAY_API_KEY` is set (Pexels optional; no AI images, no identifiable faces; you can swap any photo at qa_review, D-34), otherwise a solid brand colour. WhisperX, Remotion and FFmpeg run locally, and publishing is always mocked.

## Use it

```
docker compose up -d --build
```

Open http://localhost:8000. Type a topic, pick Short or Long, set any length (Shorts 15–180 s, Long 60–600 s; the script lands within ±15%, D-35), and start the run. The run page updates by itself: approve or edit the claims at research_review; approve, reject with notes, or edit the script yourself at script_review; watch the video and set the AI disclosure at qa_review. When the run finishes, the same page plays the video and offers every export file for download. All runs are listed on the home page.

**No login.** The UI has no authentication and the reviewer name is a text field. It is meant for a single reviewer on a local machine. Add authentication, with reviewer identity taken from the login, before deploying it anywhere.

## Limitations

- **Free tiers (D-27):** quality is below paid models, and daily quotas are small and change without notice. A run that hits the daily quota on every provider stops at `failed` before rendering, with "Retry the run after the quota resets"; re-run it the next day. Google's free tier may use prompts and responses to improve its products, so never put sensitive data in a brief.
- **Paid upgrade path:** Claude (Anthropic SDK, D-02) for the LLM steps and Sarvam for Indian-English TTS stay the documented production choice. The adapters are interfaces, so switching doesn't touch the pipeline, and cost rows already record the token counts for the estimate.
- **Shorts only** for rendering so far (D-26). Long-format scripts reach `script_review` but don't render.
- **Remotion license:** free while evaluating; check the company license before commercial use (D-26).
- Chapters (`chapters.py`) and dead-air QA (`deadair.py`) aren't wired in yet.
