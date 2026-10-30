"""Deterministic script checks (D-10, brief §07). Each returns a list of problems; empty = pass.

Script format: `## Section` headings; `[ON SCREEN: ...]` lines are visuals; every other line is
narration, with `[C#]` markers citing approved claims.
"""

import re

from app.core.contracts import Brief, Claim

WORDS_PER_SECOND = 150 / 60
SECTIONS = {
    "short": ["Hook", "Relevance", "Example", "Takeaway", "CTA"],
    "long": ["Hook", "Context", "Build", "Recap", "CTA"],
}
RUNTIME = {"short": (45, 75), "long": (180, 300)}

MARKER = re.compile(r"\[C(\d+)\]")
# Needs a source: any figure, percentage, year or calendar date.
FACTUAL = re.compile(
    r"\d|\b(january|february|march|april|may|june|july|august|september|october|november|"
    r"december)\b", re.IGNORECASE)
# Never allowed without an approved fact (brief §01 guardrails, §07 quality rules).
BANNED = re.compile(
    r"₹|\$\d|\b(salar(y|ies)|lpa|ctc|lakhs?|crores?|rs\.|placements?|placed|get hired|"
    r"job guarantee|guaranteed (job|placement|income)|earn(s|ing|ings)?|income|testimonials?|"
    r"our students|alumni|partner(s|ship|ships|ed)?|certif(ied|icate|ication)|accredited|"
    r"million (views|users|students)|\d+\s?k\+? (students|learners|users))\b", re.IGNORECASE)


def sections(script: str) -> dict[str, list[str]]:
    """Narration lines per section, in order, with visuals and blank lines removed."""
    found: dict[str, list[str]] = {}
    current = None
    for line in script.splitlines():
        line = line.strip()
        if line.startswith("## "):
            current = line[3:].strip()
            found[current] = []
        elif line and current is not None and not line.startswith("[ON SCREEN"):
            found[current].append(line)
    return found


def spoken_words(lines: list[str]) -> int:
    return sum(len(MARKER.sub("", line).split()) for line in lines)


def claim_problems(script: str, approved: list[Claim]) -> list[str]:
    ids = {c.id for c in approved}
    problems = [f"[C{n}] is not an approved claim" for n in sorted(set(MARKER.findall(script)))
                if f"C{n}" not in ids]
    narration = " ".join(line for lines in sections(script).values() for line in lines)
    for sentence in re.split(r"(?<=[.!?])\s+(?!\[C)", narration):
        if FACTUAL.search(MARKER.sub("", sentence)) and not MARKER.search(sentence):
            problems.append(f"unsourced figure or date: {sentence.strip()!r}")
    problems += [f"banned claim language: {m.group(0)!r}" for m in BANNED.finditer(script)]
    return problems


def shape_problems(script: str, brief: Brief) -> list[str]:
    found = sections(script)
    expected = SECTIONS[brief.format]
    if list(found) != expected:
        return [f"sections must be {expected}, got {list(found)}"]

    problems = [f"section {name} has no [ON SCREEN: ...] visual"
                for name in _sections_without_visuals(script)]
    seconds = {name: spoken_words(lines) / WORDS_PER_SECOND for name, lines in found.items()}
    total = sum(seconds.values())
    low, high = RUNTIME[brief.format]
    if not low <= total <= high:
        problems.append(f"runtime {total:.0f}s at 150 wpm is outside {low}-{high}s")
    if brief.format == "short":
        if seconds["Hook"] > 3:
            problems.append(f"hook takes {seconds['Hook']:.1f}s; a Short's hook must land by 3s")
        if seconds["Hook"] + seconds["Relevance"] > 10:
            problems.append("relevance must land by 10s")
    elif seconds["Hook"] > 15:
        problems.append(f"hook + outcome take {seconds['Hook']:.1f}s; limit is 15s")

    narration = " ".join(line for lines in found.values() for line in lines)
    if narration.count(brief.cta) != 1 or brief.cta not in " ".join(found["CTA"]):
        problems.append("the brief's CTA must appear exactly once, in the CTA section")
    return problems


def _sections_without_visuals(script: str) -> list[str]:
    missing: list[str] = []
    current = None
    for line in script.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            missing.append(current)
        elif line.strip().startswith("[ON SCREEN") and current in missing:
            missing.remove(current)
    return missing


def hook_line(script: str) -> str:
    return " ".join(sections(script).get("Hook", [])).strip()
