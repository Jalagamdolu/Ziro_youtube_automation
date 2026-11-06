"""Thumbnail text always fits inside 1280x720 with safe margins (D-70): one line when it fits
large, two lines when that allows a larger size. Pure layout; real fonts are checked on stills
in tests/manual_qa/thumbnails."""

import importlib

r = importlib.import_module("app.nodes.rendering")  # app.nodes.rendering is also a stage name


def wide(line: str) -> float:
    return 0.7 * len(line)  # a bold sans at size 1: ~0.7 px per character


def fits(lines: list[str], size: int) -> bool:
    width_ok = max(wide(line) for line in lines) * size <= r.THUMB_W - 2 * r.THUMB_MARGIN_X
    block = size * (len(lines) + r.LINE_GAP * (len(lines) - 1))
    return width_ok and block <= r.THUMB_H - 2 * r.THUMB_MARGIN_Y


def test_short_text_stays_on_one_line_at_the_cap() -> None:
    assert r.fit_thumbnail("RAG", wide) == (["RAG"], r.THUMB_MAX_SIZE)


def test_long_text_wraps_to_two_lines_and_fits() -> None:
    lines, size = r.fit_thumbnail("Neural Network Learning", wide)
    assert len(lines) == 2 and fits(lines, size)
    assert size > r.fit_thumbnail("Neural Network Learning", lambda _: 1e9)[1]  # bigger than 1


def test_every_existing_title_fits_the_frame() -> None:
    for text in ("Neural Network Learning", "Message Processing Path", "Numbers, Not Keywords",
                 "Host. Client. Server.", "Words Become Numbers", "Scrambled In Transit",
                 "WWWWWWWWWWWWWWWWWWWWWWWW"):
        lines, size = r.fit_thumbnail(text, wide)
        assert fits(lines, size), text
        assert " ".join(lines) == text  # no word dropped or broken
