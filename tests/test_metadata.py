from datetime import UTC, datetime

from html_content_extractor.htmlparse import parse_html
from html_content_extractor.metadata import extract_metadata


class TestExtractTitle:
    def test_prefers_og_title_over_title_tag_and_h1(self) -> None:
        root = parse_html(
            "<html><head><title>Site Name - Page</title>"
            '<meta property="og:title" content="The Real Title"></head>'
            "<body><h1>A Different Heading</h1></body></html>"
        )

        metadata = extract_metadata(root)

        assert metadata.title == "The Real Title"

    def test_falls_back_to_h1_when_no_og_title(self) -> None:
        root = parse_html(
            "<html><head><title>Site Name - Page</title></head>"
            "<body><h1>The Heading Title</h1></body></html>"
        )

        metadata = extract_metadata(root)

        assert metadata.title == "The Heading Title"

    def test_h1_title_ignores_buttons_inside_the_heading(self) -> None:
        root = parse_html(
            "<html><body><h1>Primitive Type <span>bool</span>&nbsp;"
            '<button id="copy-path">Copy item path</button></h1></body></html>'
        )

        metadata = extract_metadata(root)

        assert metadata.title == "Primitive Type bool"

    def test_falls_back_to_title_tag_when_no_h1_or_og_title(self) -> None:
        root = parse_html("<html><head><title>Only Title Tag</title></head><body></body></html>")

        metadata = extract_metadata(root)

        assert metadata.title == "Only Title Tag"

    def test_empty_when_nothing_available(self) -> None:
        root = parse_html("<html><body><p>no title anywhere</p></body></html>")

        metadata = extract_metadata(root)

        assert metadata.title == ""


class TestExtractAuthor:
    def test_reads_meta_name_author(self) -> None:
        root = parse_html('<html><head><meta name="author" content="Jane Doe"></head></html>')

        assert extract_metadata(root).author == "Jane Doe"

    def test_falls_back_to_article_author_property(self) -> None:
        root = parse_html(
            '<html><head><meta property="article:author" content="John Smith"></head></html>'
        )

        assert extract_metadata(root).author == "John Smith"

    def test_none_when_no_author_meta_present(self) -> None:
        root = parse_html("<html><head></head><body></body></html>")

        assert extract_metadata(root).author is None


class TestExtractPublishedAt:
    def test_reads_article_published_time(self) -> None:
        root = parse_html(
            '<html><head><meta property="article:published_time" '
            'content="2024-01-15T10:00:00Z"></head></html>'
        )

        published_at = extract_metadata(root).published_at

        assert published_at == datetime(2024, 1, 15, 10, 0, tzinfo=UTC)

    def test_reads_time_tag_datetime_attribute(self) -> None:
        root = parse_html(
            "<html><body><time datetime='2023-06-01T00:00:00Z'>June 1st</time></body></html>"
        )

        published_at = extract_metadata(root).published_at

        assert published_at == datetime(2023, 6, 1, tzinfo=UTC)

    def test_none_when_unparseable(self) -> None:
        root = parse_html(
            '<html><head><meta name="date" content="not a real date"></head></html>'
        )

        assert extract_metadata(root).published_at is None

    def test_none_when_absent(self) -> None:
        root = parse_html("<html><body></body></html>")

        assert extract_metadata(root).published_at is None


class TestExtractLanguage:
    def test_reads_html_lang_attribute(self) -> None:
        root = parse_html('<html lang="es"><body></body></html>')

        assert extract_metadata(root).language == "es"

    def test_falls_back_to_http_equiv_content_language(self) -> None:
        root = parse_html(
            '<html><head><meta http-equiv="Content-Language" content="fr"></head></html>'
        )

        assert extract_metadata(root).language == "fr"

    def test_none_when_no_language_signal(self) -> None:
        root = parse_html("<html><body></body></html>")

        assert extract_metadata(root).language is None
