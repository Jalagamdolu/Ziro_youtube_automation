# Host needs only Docker + make (D-16). Everything runs in the api image.
COMPOSE := docker compose
APP     := $(COMPOSE) run --rm api
CLI     := $(APP) python -m app.api.cli

FORMAT   ?= short
UNTIL    ?= end
AUDIENCE ?= Indian students, early-career developers and career switchers
CTA      ?= Explore AI learning at ziro.digital

.PHONY: up down test lint video export install-voice demo-short demo-long second-topic

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

test:
	$(COMPOSE) build api
	$(APP) pytest -q

lint:
	$(COMPOSE) build api
	$(APP) sh -c "ruff check src tests && mypy"

video:
	$(CLI) video --prompt "$(PROMPT)" --format $(FORMAT) --until $(UNTIL) --audience "$(AUDIENCE)" --cta "$(CTA)"

export:
	$(CLI) export --run $(RUN) --dest $(DEST)

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
