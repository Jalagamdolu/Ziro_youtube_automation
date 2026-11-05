"""Prompts for the production LLM steps. Built from voice.md, the vendored yt-script / yt-package
SKILL.md files and hooks.json (read, never edited), with the skills' interactive lines removed:
our three gates replace "ask the user" and "ship it, or change it?". The rules restate what
app.nodes.script_checks enforces, so a draft can pass on the first try.
"""

import json
import re
from pathlib import Path
from typing import Any

from app.core.contracts import Brief, Claim
from app.nodes import script_checks

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "vendor" / "youtube-agent-skill" / "skills"
VOICE = ROOT / "voice" / "voice.md"
EXAMPLE = Path(__file__).parent / "fixtures" / "what-makes-an-ai-agent-different-from-a-chatbot"
# Hard rules 5 and 9: the same for every brief, so they sit in the cached system prompt (D-42).
WORD_RULES = f"""# Banned and outcome words (hard rules 5 and 9)
5. Never mention salaries, placements, getting hired, earnings or income, testimonials, students
   or alumni of any institute, partnerships, certifications, user/view counts, or rupee/dollar
   amounts. Do not name Ziro's products or claim anything about Ziro beyond the CTA.
9. No hype and no invented outcomes, anywhere: narration, on-screen text, titles, thumbnail,
   description, tags. These words are rejected unless a claim in the ledger uses that exact
   word: {script_checks.OUTCOME_WORDS}. Say what the thing DOES (connects, fetches, retrieves,
   references), never how much better it makes something. A cited sentence may only say what its
   claim says.
   PASS: "How RAG Connects Models To Data" | "What Is RAG? Fetch First, Then Answer" |
         "RAG adds a retrieval step that pulls information from a new data source [C4]."
   FAIL: "Boost AI Answers With RAG" | "How RAG Fixes Hallucinations" |
         "Make LLM Answers Accurate" |
         "It references a knowledge base, improving the response [C2]."
"""


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


SUPPORT_SYSTEM = """You check a video script against its sources. For each sentence you get the
sentence and the exact quotes from the pages it cites. Decide one thing: does the sentence say
MORE than its quotes?

supported: everything the sentence states is in its quotes. Plainer wording, a shorter version,
or "you"/"your" addressed to the viewer is fine.
says more: the sentence adds something the quotes do not state: an effect or benefit ("so
answers are up to date"), a step, a cause, a comparison, scope ("always", "every"), certainty, or
a detail. Name exactly what it adds in says_more, in a few words.

You only flag; a person reads your flags and decides. Judge each sentence on its own quotes only,
not on what you know. Reply with JSON only: one verdict per sentence, in the order given."""


def support(cited: list[tuple[str, list[str]]], claims: list[Claim]) -> tuple[str, str]:
    """Support check (D-44): each cited sentence beside the quotes it cites."""
    quotes = {c.id: c.quote for c in claims}
    listed = "\n\n".join(
        f"{i + 1}. Sentence: {sentence}\n" + "\n".join(
            f"   [{cid}] quote: {quotes.get(cid, '(not an approved claim)')}" for cid in ids)
        for i, (sentence, ids) in enumerate(cited))
    return SUPPORT_SYSTEM, f"{listed}\n\nExactly {len(cited)} verdicts."


SHOT_PLAN_SYSTEM = """You plan the on-screen text of a 9:16 educational Short. The narration is
fixed; you only choose words from it to show. Reply with JSON only.

echoes: for EVERY sentence, in order, 1-4 key words copied from that sentence, shown large while
it is spoken. Pick the words that carry the idea (nouns, verbs, numbers), never filler.
pops: 1 or 2 full-screen statements for the whole video, each 2-9 words copied in order from ONE
sentence of the Relevance, Example or Takeaway sections, the line a viewer should remember;
punch: 1-2 of its words to set in serif italics (the surprising or decisive word).

Never show a word the sentence does not say. No hype or outcome words (better, faster, boost,
accurate, best, reliable, improves, fixes)."""


def shot_plan(listed: list[tuple[str, str]]) -> tuple[str, str]:
    """Shot planner (D-49): sentences as (section, text), numbered from 0."""
    lines = "\n".join(f"{i}. [{section}] {text}" for i, (section, text) in enumerate(listed))
    return SHOT_PLAN_SYSTEM, f"{lines}\n\nExactly {len(listed)} echoes."


def guidance(brief: Brief) -> str:
    """The planner's keywords and guidelines (D-47) as prompt lines; empty when unset."""
    lines = [f"Keywords: {', '.join(brief.keywords)}"] if brief.keywords else []
    lines += [f"Guidelines from the reviewer: {brief.guidelines}"] if brief.guidelines else []
    return "".join(f"{line}\n" for line in lines)


def learning_outcome(brief: Brief) -> tuple[str, str]:
    system = ("You plan short educational YouTube videos for Ziro. Reply with JSON only: "
              '{"learning_outcome": "<one sentence>"}.')
    prompt = (f"Video request: {brief.topic}\nAudience: {brief.audience}\nFormat: {brief.format}, "
              f"{brief.target_seconds} s\n\nWrite one sentence, starting with a verb, saying what "
              "the viewer can do or explain after watching. Promise only what this one video can "
              "teach; no outcomes such as jobs, salaries or placements.")
    return system, prompt


def photo_queries(brief: Brief, scenes: list[dict[str, Any]]) -> tuple[str, str]:
    system = ("You pick stock photographs for a short educational video. Reply with JSON only: "
              '{"queries": ["...", ...]}, one search phrase per scene, in order.')
    listed = "\n".join(f"{i + 1}. On screen: {s['on_screen']}\n   Narration: "
                        f"{script_checks.MARKER.sub('', s['text']).strip()}"
                        for i, s in enumerate(scenes))
    prompt = f"""Video: {brief.topic}

Visual honesty (D-40): photos for the literal, diagrams for the abstract. A scene gets a photo
ONLY if its on-screen beat or narration names a physical thing you could photograph and that IS
what the scene is about: a printed document, a phone, a classroom, a server room when the
narration is about servers. Everything else - software, models, data, ideas, steps, processes,
definitions - answers "none": that scene shows its card or diagram on the brand background. When
unsure, "none". Most scenes of a software explainer are "none".
- A photo phrase is 2-4 plain nouns naming that literal thing: "exam schedule paper", "hand
  holding phone", "server room cables". Never a stand-in (a desk, a notebook, a library, a
  keyboard) for something that isn't on a desk, in a notebook, in a library or typed.
- Never abstract words ("concept", "AI", "agent", "intelligence", "future", "innovation") and no
  metaphors.
- People only when not identifiable: hands, from behind, over the shoulder, or far away. Never
  faces, portraits, selfies or children.
- No brand names, logos, product screenshots or readable app interfaces.
- For the last scene (the call to action) write "none".
- For any scene whose card is a definition, quote, flow or checklist, write "none".

Scenes:
{listed}

Exactly {len(scenes)} phrases."""
    return system, prompt


def package(brief: Brief, claims: list[Claim], notes: str | None) -> tuple[str, str]:
    hooks = json.loads((SKILLS / "yt-script" / "hooks.json").read_text(encoding="utf-8"))
    formulas = [f"{h['name']}: {h['shape']}" for h in hooks["hooks"]]
    sections = script_checks.SECTIONS[brief.format]
    low, high = script_checks.runtime(brief)
    # D-62: a Short's requested length is a ceiling; the writer aims at 90% of it.
    fewest, target_words, most = script_checks.word_budget(brief)
    wpm = round(script_checks.speech_rate(brief) * 60)  # the voice's own rate for a Short
    words = [fewest, most]
    # Budgets scale with the requested length (D-35); Hook, Relevance and CTA stay short.
    relevance_words = min(18, max(8, target_words // 6))
    takeaway_words = max(8, round(target_words * 0.18))
    example_words = max(10, target_words - 6 - relevance_words - takeaway_words
                        - len(brief.cta.split()))
    shape = (f"Word budget per section: Hook 5-7 words (it must land within 3 s); Relevance "
             f"about {relevance_words} (relevance lands by 10 s); Example about {example_words}, "
             f"one worked example told step by step; Takeaway about {takeaway_words}, one "
             f"practical test or rule; "
             f"CTA just the CTA line. Count your words: drafts under {words[0]} or over "
             f"{words[1]} words are rejected. The finished Short, pauses included, must not "
             f"run longer than {brief.target_seconds} s, so never go past that word count."
             if brief.format == "short" else
             "Hook (including the learning outcome) at most 37 spoken words (15 s); Context with "
             "prerequisites; Build is the step-by-step demonstration; Recap names one limitation "
             "and the next action.")
    # hookscore.py prefers longer hooks; for a Short the brief's 3-second rule wins (D-21), so
    # every candidate is short and whichever two score best still fit.
    hook_length = ("Every hook is 5-7 words." if brief.format == "short"
                   else "Every hook is at most 25 words.")
    body = " and ".join(script_checks.BODY[brief.format])
    # Everything in the system prompt is the same for every brief, so Claude caches it (D-42).
    system = "\n\n".join([
        "You write YouTube scripts and packaging for Ziro (written \"Ziro\"). Reply with one JSON "
        "object only. Follow the voice profile and the hard rules exactly; a deterministic checker "
        "rejects any draft that breaks a hard rule.",
        "# Voice profile (voice.md)\n" + VOICE.read_text(encoding="utf-8"),
        "# Scripting method (yt-script)\n" + skill("yt-script"),
        "# Hook rules (hooks.json)\n" + "\n".join(f"- {r}" for r in hooks["rules"])
        + "\n## Formulas\n" + "\n".join(f"- {f}" for f in formulas),
        "# Packaging method (yt-package)\n" + skill("yt-package"),
        WORD_RULES,
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
3. Narration: {words[0]}-{words[1]} spoken words in total ({wpm} words per minute, {low}-{high} s);
   aim for about {target_words}.
   {shape}
4. Every sentence that uses a fact from the claim ledger ends with its marker, e.g. "[C2]". Use
   only the ledger's facts, in its wording or a faithful paraphrase. Any sentence with a digit,
   year or month name needs a marker. Write numbers as words only if they are not facts.
   In the {body} section every sentence ends with a marker, except a question, a labelled
   illustration (starting "For example", "Imagine", "Suppose" or "Say you") or a line spoken
   to the viewer (starting "You", "If you", "Try" or "Let's"). Anything else is uncited.
5. Banned topics: see "Banned and outcome words" in the system prompt.
6. The CTA section contains the CTA exactly once, verbatim: "{brief.cta}". It appears nowhere else.
7. The Hook section's narration is exactly the text of one of your five hooks.
8. hooks: five distinct hooks, each with a one-sentence explanation naming its formula.
   {hook_length}
9. No hype and no invented outcomes: see "Banned and outcome words" in the system prompt.
10. titles: ten distinct titles, at most 60 characters, no more than two ALL-CAPS words.
11. thumbnail_text: at most 3 words, not repeating words from the best title.
12. description: 2-4 plain sentences, then "Sources:" with one line per cited claim
    ("- <publisher>, <page title>: <url>"), then the CTA line.
13. tags: at most 15. target_queries: exactly 3 search phrases. chapters: start at 0 seconds,
    one per section, using start_seconds from the 150 wpm estimate.{{explainer}}

# JSON shape
{{"script": "...", "hooks": [{{"text": "...", "explanation": "..."}}], "titles": ["..."],
 "thumbnail_text": "...", "description": "...", "tags": ["..."], "target_queries": ["..."],
 "chapters": [{{"start_seconds": 0, "title": "..."}}]}}"""
    if script_checks.is_explainer(brief.topic):
        mechanism = ", ".join(c.id for c in claims if c.kind == "mechanism")
        rules = rules.replace("{explainer}", f"""
14. This is an explainer ("{brief.topic}"): the viewer must leave knowing HOW it works.
    - Relevance stays on the topic: the problem this thing solves, in one plain line. No career,
      portfolio, job or project lines.
    - Example explains the mechanism step by step, one step per sentence, citing the mechanism
      claims ({mechanism}); at least {script_checks.MIN_MECHANISM} of them. A flow visual's steps
      are the steps those sentences say.
    - Hook asks or states what it is or how it works; not a side benefit.""")
    else:
        rules = rules.replace("{explainer}", "")
    ledger = "\n".join(f"[{c.id}] ({c.kind}) {c.claim} (source: {c.title}, {c.url}"
                       + (f", published {c.published_at.date()}" if c.published_at else "") + ")"
                       for c in claims)
    example = (EXAMPLE / "script.md").read_text(encoding="utf-8").replace("{cta}", brief.cta)
    prompt = "\n\n".join(filter(None, [
        rules,
        f"# Brief\nTopic: {brief.topic}\nAudience: {brief.audience}\nLearning outcome: "
        f"{brief.learning_outcome}\nLanguage: {brief.language}\nFormat: {brief.format}, target "
        f"{brief.target_seconds} s\nCTA: {brief.cta}\n{guidance(brief)}",
        f"# Claim ledger (the only facts you may state)\n{ledger}",
        "# Example of the script format (a Short on another topic; copy the format, not the "
        f"content)\n{example}" if brief.format == "short" else "",
        f"# Revision required\nYour previous draft was rejected. {notes}\nWrite a complete new "
        "draft that fixes every point." if notes else "",
    ]))
    return system, prompt
