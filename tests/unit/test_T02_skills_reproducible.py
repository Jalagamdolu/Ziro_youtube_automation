"""T02: the vendored skill tools run from a fresh checkout, with no manual copy-paste step."""

from app.nodes import skills


def test_vendored_pack_is_complete() -> None:
    folders = sorted(p.name for p in skills.SKILLS.iterdir() if p.is_dir())
    assert len(folders) == 11 and all((skills.SKILLS / f / "SKILL.md").exists() for f in folders)
    assert (skills.SKILLS.parent / "LICENSE").read_text().startswith("MIT License")


def test_hookscore_runs_and_ranks() -> None:
    scored = skills.score_hooks(["Why does your chatbot stop before work?",
                                 "Your chatbot answers. An agent acts."])
    assert [h["hook"] for h in scored][0] == "Why does your chatbot stop before work?"
    assert {"verdict", "band", "formula", "properties"} <= scored[0].keys()


def test_title_lint_flags_thumbnail_repeats() -> None:
    linted = skills.lint_titles(["AI Agent vs Chatbot for Students"], "AGENT VS CHATBOT")
    assert ("duplicate" in {issue for issue, _ in linted[0]["issues"]})
