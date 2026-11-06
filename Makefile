# Host needs only Docker + make (D-16). Everything runs in the api image.
COMPOSE := docker compose
APP     := $(COMPOSE) run --rm api
CLI     := $(APP) python -m app.api.cli

FORMAT   ?= short
UNTIL    ?= end
AUDIENCE ?= Indian students, early-career developers and career switchers
CTA      ?= Explore AI learning at ziro.digital

.PHONY: up down test test-live lint secret-scan video export install-voice youtube-auth archive demo-short demo-long second-topic

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

test:
	$(COMPOSE) build api
	$(APP) pytest -q

# Free-tier smoke test (D-27): a few real requests; keys from .env.
test-live:
	$(COMPOSE) build api
	$(APP) sh -c "ZIRO_LIVE=1 pytest -q -m live"

lint:
	$(COMPOSE) build api
	$(APP) sh -c "ruff check src tests && mypy"

# D-41: fail if any tracked file holds an API key (Google AIza/AQ., Groq, Tavily, Anthropic).
# Saved third-party pages (manual QA evidence) carry Google's own public page keys; skipped.
SECRET_PATTERN = AIza[0-9A-Za-z_-]{20,}|AQ\.[0-9A-Za-z_-]{20,}|gsk_[0-9A-Za-z]{20,}|tvly-[0-9A-Za-z_-]{16,}|sk-ant-[0-9A-Za-z_-]{20,}
secret-scan:
	@! git grep -nIE '$(SECRET_PATTERN)' -- . ':!tests/manual_qa/source-snapshots' || { echo "secret-scan: API key found in a tracked file (above); remove it and revoke the key"; exit 1; }

video:
	$(CLI) video --prompt "$(PROMPT)" --format $(FORMAT) --until $(UNTIL) --audience "$(AUDIENCE)" --cta "$(CTA)"

export:
	$(CLI) export --run $(RUN) --dest $(DEST)

archive:  # hide (never delete) videos created before BEFORE=YYYY-MM-DD, IST (D-73)
	$(CLI) archive --before $(BEFORE)

youtube-auth:  # on the host, not in a container: the browser redirects to 127.0.0.1 (D-67)
	PYTHONPATH=src python -m app.api.youtube_auth

install-voice:
	mkdir -p ~/.claude/youtube
	cp src/voice/voice.md ~/.claude/youtube/voice.md

demo-short:
	$(MAKE) video FORMAT=short AUDIENCE="Indian students" \
		PROMPT="What makes an AI agent different from a chatbot?"

demo-long:
	$(MAKE) video FORMAT=long AUDIENCE="Python beginners" \
		PROMPT="Build a simple agent workflow for résumé feedback. State that it is an illustrative educational build, not a real recruitment decision system."

second-topic:
	$(MAKE) video FORMAT=long UNTIL=script_review \
		PROMPT="Three practical GenAI portfolio projects for freshers. No placement or salary claims."
