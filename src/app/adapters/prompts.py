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
    shape = ("Word budget per section: Hook 5-7 words (it must land within 3 s); Relevance "
             "12-18 (relevance lands by 10 s); Example 70-95, one worked example told step by "
             "step; Takeaway 20-30, one practical test or rule; CTA just the CTA line. Count "
             "your words: drafts under 112 words are rejected."
             if brief.format == "short" else
             "Hook (including the learning outcome) at most 37 spoken words (15 s); Context with "
             "prerequisites; Build is the step-by-step demonstration; Recap names one limitation "
             "and the next action.")
    # hookscore.py prefers longer hooks; for a Short the brief's 3-second rule wins (D-21), so
    # every candidate is short and whichever two score best still fit.
    hook_length = ("Every hook is 5-7 words." if brief.format == "short"
                   else "Every hook is at most 25 words.")
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
2. Every section has at least one visual line before its narration, written in exactly one of
   these forms (anything else renders as a plain title card):
   [ON SCREEN: definition card - "Headline", source: Publisher]   narration under it cites a claim
   [ON SCREEN: quote card - "Page title", source: Publisher]      narration under it cites a claim
   [ON SCREEN: "Thing A" and "Thing B" side by side]
   [ON SCREEN: chat bubble asking "the user's exact message"]
   [ON SCREEN: flow - "Step one" to "Step two" to "Step three"]
   [ON SCREEN: checklist - "First item" / "Second item"]
   [ON SCREEN: Ziro logo and "ziro.digital"]                      CTA section only
   [ON SCREEN: "Short headline"]                                   anything else
   Visuals are illustrations and text cards only: no real product screens, no people. Words in
   quotes on screen must be words the narration says; never show a word the voice doesn't.
3. Narration: {words[0]}-{words[1]} spoken words in total (150 words per minute, {low}-{high} s);
   aim for about {sum(words) // 2}.
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
   {hook_length}
9. Narration, on-screen text, titles, thumbnail text, description and tags use no outcome or
   quality words (fixes, solves, better, faster, accurate, reliable, hallucinations, best, #1,
   reduces, improves, boost) unless a claim in the ledger uses that exact word.
10. titles: ten distinct titles, at most 60 characters, no more than two ALL-CAPS words.
11. thumbnail_text: at most 3 words, not repeating words from the best title.
12. description: 2-4 plain sentences, then "Sources:" with one line per cited claim
    ("- <publisher>, <page title>: <url>"), then the CTA line.
13. tags: at most 15. target_queries: exactly 3 search phrases. chapters: start at 0 seconds,
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
