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


def test_cues_stop_at_three_words_and_at_sentence_ends() -> None:
    tokens = ["one", "two", "three", "four", "five.", "six", "seven"]
    words = [{"text": t, "start": float(i), "end": i + 0.5} for i, t in enumerate(tokens)]
    cues = make_cues(words)
    assert [len(c["words"]) for c in cues] == [3, 2, 2]  # D-37: 2-3 big words at a time
    assert to_srt(cues).startswith("1\n00:00:00,000 --> 00:00:02,500\none two three")
    assert to_vtt(cues).startswith("WEBVTT\n\n00:00:00.000 --> 00:00:02.500\n")


def test_whisperx_may_split_our_sentence_in_two() -> None:
    """Run 550b71f2: a period inside quotes. We synthesise one sentence; WhisperX's own sentence
    splitter returns two segments. Words must still come back in order, none lost."""
    from app.adapters.aligner import WhisperXAligner

    class FakeWhisperX:
        def align(self, segments, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return {"segments": [
                {"start": 0.0, "words": [{"word": "Ask", "start": 0.0, "end": 0.3},
                                         {"word": "“Build", "start": 0.3, "end": 0.6},
                                         {"word": "it.”", "start": 0.6, "end": 0.9}]},
                {"start": 1.0, "words": [{"word": "It", "start": 1.0, "end": 1.2},
                                         {"word": "2026."}]}]}  # an unplaceable token

    aligner = WhisperXAligner.__new__(WhisperXAligner)
    aligner.whisperx, aligner.model, aligner.metadata = FakeWhisperX(), None, None
    words = aligner.align(None, [{"text": 'Ask “Build it.” It 2026.', "start": 0.0, "end": 2.0}])
    assert [w["text"] for w in words] == ["Ask", "“Build", "it.”", "It", "2026."]
    assert words[-1]["start"] == 1.2  # inherits its neighbour's end


def test_a_closing_quote_still_ends_the_sentence() -> None:
    line = "Ask the model: “Create an app for a startup.” The model writes it."
    assert sentences([line]) == ["Ask the model: “Create an app for a startup.”",
                                 "The model writes it."]
    words = [{"text": t, "start": i, "end": i + 1} for i, t in enumerate(
        ["a", "startup.”", "The", "model"])]
    assert [len(c["words"]) for c in make_cues(words)] == [2, 2]
