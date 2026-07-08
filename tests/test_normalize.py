import unicodedata

from html_content_extractor.normalize import collapse_whitespace, normalize_text


class TestCollapseWhitespace:
    def test_collapses_repeated_spaces_and_tabs(self) -> None:
        assert collapse_whitespace("a   b\t\tc") == "a b c"

    def test_strips_leading_and_trailing_whitespace(self) -> None:
        assert collapse_whitespace("  hello  ") == "hello"

    def test_preserves_newlines(self) -> None:
        assert collapse_whitespace("line one\nline two") == "line one\nline two"


class TestNormalizeText:
    def test_converts_decomposed_form_to_nfc(self) -> None:
        decomposed = "cafe" + "́"  # "e" + acute accent combinante
        normalized = normalize_text(decomposed)

        assert normalized == unicodedata.normalize("NFC", decomposed)
        assert normalized == "café"

    def test_collapses_three_or_more_blank_lines_to_two(self) -> None:
        text = "first\n\n\n\n\nsecond"

        assert normalize_text(text) == "first\n\nsecond"

    def test_collapses_inline_whitespace(self) -> None:
        assert normalize_text("a   b") == "a b"
