"""Tests for app/services/legal_synonyms.py."""

from app.services.legal_synonyms import expand_query


def test_adds_legal_terms_and_keeps_the_original_question():
    expanded = expand_query("Can I use a song?")

    assert expanded.startswith("Can I use a song?")
    assert "musical work" in expanded


def test_matches_plural_and_past_tense():
    assert "musical work" in expand_query("I use songs")
    assert "refusal" in expand_query("my application was rejected")


def test_matches_whole_words_only():
    # "copy" must not match inside "copyright", "app" must not match inside "apply"
    assert expand_query("copyright") == "copyright"
    assert expand_query("apply") == "apply"


def test_matches_phrases():
    assert "term duration" in expand_query("How long is it valid?")


def test_question_without_everyday_words_is_unchanged():
    assert expand_query("Registrar of Copyrights") == "Registrar of Copyrights"
