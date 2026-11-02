"""Prompts for the production LLM steps. Built from voice.md, the vendored yt-script / yt-package
SKILL.md files and hooks.json (read, never edited), with the skills' interactive lines removed:
our three gates replace "ask the user" and "ship it, or change it?". The rules restate what
app.nodes.script_checks enforces, so a draft can pass on the first try.
"""

import json
import re
from pathlib import Path

from app.core.contracts import Brief, Claim
from app.nodes import script_checks
from app.nodes.storyboarding import VISUAL_TYPES

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "vendor" / "youtube-agent-skill" / "skills"
VOICE = ROOT / "voice" / "voice.md"
EXAMPLE = Path(__file__).parent / "fixtures" / "what-makes-an-ai-agent-different-from-a-chatbot"


def skill(name: str) -> str:
    """SKILL.md body without front matter, tool-usage blocks, 'The gate' and ask-the-user lines."""
    text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    text = re.sub(r"\A---.*?---\s*", "", text, flags=re.DOTALL)
    text = re.sub(r"```.*?```\s*", "", text, flags=re.DOTALL)
    text = re.sub(r"## The gate.*", "", text, flags=re.DOTALL)
    keep = [line for line in text.splitlines()
            if not re.search(r"\bask (for|the user)|show the user|ship it|hookscore\.py|title\.py",
                             line, re.IGNORECASE)]
    return "\n".join(keep).strip()


def learning_outcome(brief: Brief) -> tuple[str, str]:
    system = ("You plan short educational YouTube videos for Ziro. Reply with JSON only: "
              '{"learning_outcome": "<one sentence>"}.')
    prompt = (f"Video request: {brief.topic}\nAudience: {brief.audience}\nFormat: {brief.format}, "
              f"{brief.target_seconds} s\n\nWrite one sentence, starting with a verb, saying what "
              "the viewer can do or explain after watching. Promise only what this one video can "
              "teach; no outcomes such as jobs, salaries or placements.")
    return system, prompt


def package(brief: Brief, claims: list[Claim], notes: str | None) -> tuple[str, str]:
    hooks = json.loads((SKILLS / "yt-script" / "hooks.json").read_text(encoding="utf-8"))
    formulas = [f"{h['name']}: {h['shape']}" for h in hooks["hooks"]]
    sections = script_checks.SECTIONS[brief.format]
    low, high = script_checks.RUNTIME[brief.format]
    words = [round(s * script_checks.WORDS_PER_SECOND) for s in (low, high)]
    visuals = ", ".join(f'"{key}"' for key, _ in VISUAL_TYPES)
    shape = ("Hook at most 7 spoken words (it must land within 3 s); Hook + Relevance at most 25 "
             "words (relevance lands by 10 s); one worked example; one takeaway."
             if brief.format == "short" else
             "Hook (including the learning outcome) at most 37 spoken words (15 s); Context with "
             "prerequisites; Build is the step-by-step demonstration; Recap names one limitation "
             "and the next action.")
    system = "\n\n".join([
        "You write YouTube scripts and packaging for Ziro (written \"Ziro\"). Reply with one JSON "
        "object only. Follow the voice profile and the hard rules exactly; a deterministic checker "
        "rejects any draft that breaks a hard rule.",
        "# Voice profile (voice.md)\n" + VOICE.read_text(encoding="utf-8"),
        "# Scripting method (yt-script)\n" + skill("yt-script"),
        "# Hook rules (hooks.json)\n" + "\n".join(f"- {r}" for r in hooks["rules"])
        + "\n## Formulas\n" + "\n".join(f"- {f}" for f in formulas),
        "# Packaging method (yt-package)\n" + skill("yt-package"),
    ])
    rules = f"""# Hard rules
1. Script format: Markdown. Exactly these sections, in order, as "## Name" headings:
   {", ".join(sections)}.
2. Every section has at least one visual line "[ON SCREEN: ...]" before its narration. Start each
   visual with one of {visuals} when it fits; put on-screen words in double quotes; a definition
   or quote card names its source as "source: <publisher>". Visuals are illustrations and text
   cards only: no real product screens, no people, no logos except "Ziro logo".
3. Narration: {words[0]}-{words[1]} spoken words in total (150 words per minute, {low}-{high} s).
   {shape}
4. Every sentence that uses a fact from the claim ledger ends with its marker, e.g. "[C2]". Use
   only the ledger's facts, in its wording or a faithful paraphrase. Any sentence with a digit,
   year or month name needs a marker. Write numbers as words only if they are not facts.
5. Never mention salaries, placements, getting hired, earnings or income, testimonials, students
   or alumni of any institute, partnerships, certifications, user/view counts, or rupee/dollar
   amounts. Do not name Ziro's products or claim anything about Ziro beyond the CTA.
6. The CTA section contains the CTA exactly once, verbatim: "{brief.cta}". It appears nowhere else.
7. The Hook section's narration is exactly the text of one of your five hooks.
8. hooks: five distinct hooks, each with a one-sentence explanation naming its formula.
9. titles: ten distinct titles, at most 60 characters, no more than two ALL-CAPS words.
10. thumbnail_text: at most 3 words, not repeating words from the best title.
11. description: 2-4 plain sentences, then "Sources:" with one line per cited claim
    ("- <publisher>, <page title>: <url>"), then the CTA line.
12. tags: at most 15. target_queries: exactly 3 search phrases. chapters: start at 0 seconds,
    one per section, using start_seconds from the 150 wpm estimate.

# JSON shape
{{"script": "...", "hooks": [{{"text": "...", "explanation": "..."}}], "titles": ["..."],
 "thumbnail_text": "...", "description": "...", "tags": ["..."], "target_queries": ["..."],
 "chapters": [{{"start_seconds": 0, "title": "..."}}]}}"""
    ledger = "\n".join(f"[{c.id}] {c.claim} (source: {c.title}, {c.url}"
                       + (f", published {c.published_at.date()}" if c.published_at else "") + ")"
                       for c in claims)
    example = (EXAMPLE / "script.md").read_text(encoding="utf-8").replace("{cta}", brief.cta)
    prompt = "\n\n".join(filter(None, [
        rules,
        f"# Brief\nTopic: {brief.topic}\nAudience: {brief.audience}\nLearning outcome: "
        f"{brief.learning_outcome}\nLanguage: {brief.language}\nFormat: {brief.format}, target "
        f"{brief.target_seconds} s\nCTA: {brief.cta}",
        f"# Claim ledger (the only facts you may state)\n{ledger}",
        "# Example of the script format (a Short on another topic; copy the format, not the "
        f"content)\n{example}" if brief.format == "short" else "",
        f"# Revision required\nYour previous draft was rejected. {notes}\nWrite a complete new "
        "draft that fixes every point." if notes else "",
    ]))
    return system, prompt
