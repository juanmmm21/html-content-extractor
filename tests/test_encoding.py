from html_content_extractor.encoding import resolve_encoding

_ORIGINAL = "El café en España cuesta más de lo que parece."


class TestResolveEncodingCleanText:
    def test_leaves_clean_utf8_text_untouched(self) -> None:
        html = f"<html><body><p>{_ORIGINAL}</p></body></html>"

        text, encoding_used = resolve_encoding(html, content_type_header=None)

        assert text == html
        assert encoding_used == "utf-8"

    def test_defaults_assumed_encoding_to_header_charset_when_present(self) -> None:
        html = f"<html><body><p>{_ORIGINAL}</p></body></html>"

        _, encoding_used = resolve_encoding(
            html, content_type_header="text/html; charset=iso-8859-1"
        )

        assert encoding_used == "iso-8859-1"


class TestResolveEncodingMojibakeCorrection:
    def test_corrects_utf8_bytes_misdecoded_as_latin1_using_meta_charset(self) -> None:
        mojibake = _ORIGINAL.encode("utf-8").decode("iso-8859-1")
        html = f'<html><head><meta charset="utf-8"></head><body><p>{mojibake}</p></body></html>'

        text, encoding_used = resolve_encoding(
            html, content_type_header="text/html; charset=iso-8859-1"
        )

        assert "café" in text
        assert "España" in text
        assert encoding_used == "utf-8"

    def test_corrects_using_http_equiv_meta_tag(self) -> None:
        mojibake = _ORIGINAL.encode("utf-8").decode("windows-1252")
        html = (
            '<html><head><meta http-equiv="Content-Type" '
            'content="text/html; charset=utf-8"></head>'
            f"<body><p>{mojibake}</p></body></html>"
        )

        text, encoding_used = resolve_encoding(
            html, content_type_header="text/html; charset=windows-1252"
        )

        assert "café" in text
        assert encoding_used == "utf-8"

    def test_falls_back_to_common_utf8_windows1252_confusion_without_meta(self) -> None:
        mojibake = _ORIGINAL.encode("utf-8").decode("windows-1252")
        html = f"<html><body><p>{mojibake}</p></body></html>"

        text, encoding_used = resolve_encoding(
            html, content_type_header="text/html; charset=windows-1252"
        )

        assert "café" in text
        assert encoding_used == "utf-8"

    def test_gives_up_gracefully_when_no_candidate_helps(self) -> None:
        # Texto con marcador de mojibake que no corresponde a ninguna confusión real:
        # ninguna re-decodificación reducirá los marcadores, así que se debe devolver
        # el texto de entrada sin modificar en vez de lanzar o degradar el texto más.
        html = "<html><body><p>Ã plain text without a real encoding mismatch</p></body></html>"

        text, encoding_used = resolve_encoding(html, content_type_header=None)

        assert text == html
        assert encoding_used == "utf-8"

    def test_never_raises_on_unknown_declared_charset(self) -> None:
        html = (
            '<html><head><meta charset="not-a-real-charset"></head>'
            "<body><p>Ã broken looking text</p></body></html>"
        )

        text, encoding_used = resolve_encoding(html, content_type_header=None)

        assert text == html
        assert encoding_used == "utf-8"
