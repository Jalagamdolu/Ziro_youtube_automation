"""Pronunciation (brief §07: written "Ziro", spoken "ZAIRO"), word-timed captions and SRT/VTT."""

from app.adapters.aligner import EvenAligner
from app.adapters.tts import spoken_parts, spoken_text
from app.nodes.rendering import make_cues, sentences, to_srt, to_vtt, written_words

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


def test_captions_show_written_brand_with_spoken_timing() -> None:
    written = "Explore AI learning at ziro.digital."
    segment = {"text": spoken_text(written, PRONUNCIATION), "written": written,
               "start": 1.0, "end": 4.0}
    spoken = EvenAligner().align(None, [segment])
    assert [w["text"] for w in spoken][-3:] == ["Ziro", "dot", "digital."]
    words = written_words(spoken, [segment])
    assert [w["text"] for w in words] == ["Explore", "AI", "learning", "at", "ziro.digital."]
    assert words[-1]["start"] == spoken[-3]["start"] and words[-1]["end"] == 4.0


def test_cues_stop_at_five_words_and_at_sentence_ends() -> None:
    tokens = ["one", "two", "three", "four", "five", "six.", "seven"]
    words = [{"text": t, "start": float(i), "end": i + 0.5} for i, t in enumerate(tokens)]
    cues = make_cues(words)
    assert [len(c["words"]) for c in cues] == [5, 1, 1]
    assert to_srt(cues).startswith("1\n00:00:00,000 --> 00:00:04,500\none two three four five")
    assert to_vtt(cues).startswith("WEBVTT\n\n00:00:00.000 --> 00:00:04.500\n")
