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
# Function words carry no content, so the screen may show them unspoken (D-29).
FILLER = {"what", "when", "where", "which", "while", "who's", "whose", "that", "this", "these",
          "those", "then", "than", "there", "their", "they", "them", "your", "you're", "with",
          "without", "from", "into", "onto", "about", "does", "doesn't", "have", "just", "only",
          "also", "each", "every", "here", "more", "most", "some", "such", "very", "will", "would",
          "should", "could", "it's", "isn't", "can't", "don't"}
# Outcome and quality claims; in packaging only when an approved claim uses the same word.
OUTCOME = re.compile(
    r"#1|\b(hallucinat\w*|accura\w*|error[- ]free|reliab\w*|fix(es|ed)?|solv(e|es|ed)|"
    r"eliminat\w*|prevent\w*|guarantee\w*|proven|best|number one|better|faster|cheaper|"
    r"outperform\w*|reduc\w*|improv\w*|boost\w*|perfect\w*|\d+x)\b", re.IGNORECASE)


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
    # Outcome words ("improves", "reliable") are claims even without a figure (D-29).
    ledger = " ".join(f"{c.claim} {c.quote}" for c in approved).lower()
    problems += [f"narration claims {m.group(0)!r}; no approved claim says it, so leave it out"
                 for m in OUTCOME.finditer(narration) if m.group(0).lower()[:5] not in ledger]
    return problems


def on_screen_problems(script: str, approved: list[Claim], topic: str) -> list[str]:
    """On-screen words carry no [C#] markers either: they get the packaging scan, and the screen
    may only show words the narration says (or the topic / a cited source's page title), so
    screen and voice never disagree."""
    shown = [q for line in script.splitlines() if line.strip().startswith("[ON SCREEN")
             for q in re.findall(r'"([^"]+)"', line)]
    narration = " ".join(line for lines in sections(script).values() for line in lines)
    # "example" / "illustrative" label a flow as made up, which is a disclosure, not a claim.
    allowed = " ".join([narration, topic, "example illustrative",
                        *(c.title for c in approved)]).lower()
    problems = packaging_problems(shown, approved)
    for text in shown:
        for word in re.findall(r"[a-z][a-z'-]{3,}", text.lower()):
            stem = word.removesuffix("s")[:5]
            if word not in FILLER and stem not in allowed:
                problems.append(f"on-screen {text!r} shows {word!r}, which the narration never "
                                f"says: say {word!r} in the narration under that visual, or "
                                "change the on-screen words")
    return problems


def packaging_problems(texts: list[str], approved: list[Claim]) -> list[str]:
    """Titles, thumbnail, description and tags carry no [C#] markers, so they may not make a
    claim at all: banned language is refused, and an outcome word ("fixes", "hallucinations",
    "better") is refused unless an approved claim itself uses it."""
    ledger = " ".join(f"{c.claim} {c.quote}" for c in approved).lower()
    problems: list[str] = []
    for text in texts:
        body = text.split("Sources:")[0]  # the description's source list is ours, not a claim
        problems += [f"banned claim language in packaging: {m.group(0)!r} in {text[:60]!r}"
                     for m in BANNED.finditer(body)]
        problems += [f"packaging claims {m.group(0)!r} ({text[:60]!r}); no approved claim says "
                     "it, so leave it out" for m in OUTCOME.finditer(body)
                     if m.group(0).lower()[:5] not in ledger]
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
        words, middle = round(total * WORDS_PER_SECOND), round((low + high) / 2 * WORDS_PER_SECOND)
        problems.append(f"runtime {total:.0f}s ({words} spoken words) at 150 wpm is outside "
                        f"{low}-{high}s: {'add' if words < middle else 'cut'} about "
                        f"{abs(middle - words)} spoken words in the {expected[2]} section")
    if brief.format == "short":
        if seconds["Hook"] > 3:
            problems.append(f"hook takes {seconds['Hook']:.1f}s; a Short's hook must land by 3s "
                            "(at most 7 words)")
        if seconds["Hook"] + seconds["Relevance"] > 10:
            used = round((seconds["Hook"] + seconds["Relevance"]) * WORDS_PER_SECOND)
            problems.append(f"relevance must land by 10s: Hook + Relevance have {used} words, "
                            "at most 25; move the extra words into Example")
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
