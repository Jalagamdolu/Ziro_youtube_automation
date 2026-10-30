"""Pronunciation handling (brief §07: written "Ziro", spoken "ZAIRO") and SRT timing."""

from app.adapters.tts import spoken_parts
from app.nodes.rendering import sentences, split_cue, to_srt

PRONUNCIATION = {"replace": {"ziro.digital": "Ziro dot digital"}, "phonemes": {"Ziro": "zˈaɪɹoʊ"}}


def test_brand_is_spoken_as_zairo_phonemes() -> None:
    parts = spoken_parts("Explore AI learning at ziro.digital.", PRONUNCIATION)
    assert parts == [("Explore AI learning at ", False), ("zˈaɪɹoʊ", True),
                     (" dot digital.", False)]


def test_text_without_dictionary_words_is_untouched() -> None:
    assert spoken_parts("An agent acts.", PRONUNCIATION) == [("An agent acts.", False)]


def test_sentences_drop_claim_markers() -> None:
    assert sentences(["A chatbot talks. [C2]", "An agent acts!"]) == ["A chatbot talks.",
                                                                     "An agent acts!"]


def test_cues_cover_the_sentence_exactly() -> None:
    cues = split_cue(2.0, 5.0, "one two three four five six seven")
    assert [c[2] for c in cues] == ["one two three four five", "six seven"]
    assert cues[0][0] == 2.0 and abs(cues[-1][1] - 5.0) < 1e-9
    assert to_srt(cues).startswith("1\n00:00:02,000 --> 00:00:04,")
