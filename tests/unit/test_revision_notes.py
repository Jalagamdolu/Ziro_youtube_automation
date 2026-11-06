"""A length cut reaches the reviser word for word, first (D-71), so revisions shorten."""

from app.nodes.scripting import revision_notes

CUT = ("with its pauses the Short would run 52.3s; it was asked for at most 30s: cut about 68 "
       "spoken words in the Example section")


def test_a_length_cut_leads_the_revision_notes_with_the_exact_count() -> None:
    notes = revision_notes("", ["the five hooks must be distinct", CUT], "## Hook\nHi")
    assert notes.startswith("LENGTH FIRST — the script is too long: " + CUT)
    assert "Fix: the five hooks must be distinct; " + CUT in notes
    assert notes.endswith("to revise rather than restart:\n## Hook\nHi")


def test_other_problems_keep_the_plain_fix_list() -> None:
    notes = revision_notes("Reviewer notes: shorter\n", ["the five hooks must be distinct"], "x")
    assert notes.startswith("Reviewer notes: shorter\nFix: the five hooks")
    assert "LENGTH" not in notes
