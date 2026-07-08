import json
from pathlib import Path

from html_content_extractor.models import DiscardReason, ExtractionConfig
from html_content_extractor.pipeline import ExtractionPipeline

_LONG_ARTICLE_HTML = """
<html lang="en"><head><title>Long Article</title>
<meta property="og:title" content="A Long Article About Search"></head>
<body>
<header><nav><a href="/">Home</a></nav></header>
<article class="post-content">
<h1>A Long Article About Search</h1>
<p>This paragraph contains a substantial amount of real prose about how search engines
work, why inverted indexes matter, and how relevance ranking combines multiple signals
together to produce a useful ordering of results for the end user.</p>
<p>This second paragraph continues with more depth on tokenization, tolerant HTML
parsing, and the general engineering trade-offs involved in building a search engine
completely from scratch without leaning on any third-party indexing library.</p>
</article>
<footer><p>Copyright Example Corp.</p></footer>
</body></html>
"""


def _write_pages_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
    )


def _base_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "url": "http://example.com/article",
        "final_url": "http://example.com/article",
        "status_code": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "html": _LONG_ARTICLE_HTML,
        "fetched_at": "2024-01-15T09:00:00+00:00",
        "depth": 1,
        "content_type": "text/html",
    }
    record.update(overrides)
    return record


class TestExtractionPipelineRun:
    def test_extracts_a_valid_article_into_documents_jsonl(self, tmp_path: Path) -> None:
        pages_path = tmp_path / "pages.jsonl"
        _write_pages_jsonl(pages_path, [_base_record()])
        documents_path = tmp_path / "documents.jsonl"
        discarded_path = tmp_path / "discarded.jsonl"

        with ExtractionPipeline(ExtractionConfig(), documents_path, discarded_path) as pipeline:
            stats = pipeline.run(pages_path)

        assert stats.pages_extracted == 1
        assert stats.pages_discarded == 0

        documents = [
            json.loads(line) for line in documents_path.read_text(encoding="utf-8").splitlines()
        ]
        assert len(documents) == 1
        document = documents[0]
        assert document["title"] == "A Long Article About Search"
        assert "substantial amount of real prose" in document["main_text"]
        assert "Copyright Example Corp" not in document["main_text"]
        assert document["language"] == "en"
        assert document["depth"] == 1
        assert document["word_count"] > 0

    def test_discards_non_html_content_type_without_parsing(self, tmp_path: Path) -> None:
        pages_path = tmp_path / "pages.jsonl"
        _write_pages_jsonl(
            pages_path,
            [_base_record(headers={"Content-Type": "application/pdf"}, html="%PDF-1.4 ...")],
        )
        documents_path = tmp_path / "documents.jsonl"
        discarded_path = tmp_path / "discarded.jsonl"

        with ExtractionPipeline(ExtractionConfig(), documents_path, discarded_path) as pipeline:
            stats = pipeline.run(pages_path)

        assert stats.pages_extracted == 0
        assert stats.pages_discarded == 1
        assert stats.discard_counts[DiscardReason.NON_HTML_CONTENT] == 1
        assert not documents_path.exists() or documents_path.read_text() == ""

        discarded = [
            json.loads(line) for line in discarded_path.read_text(encoding="utf-8").splitlines()
        ]
        assert discarded[0]["reason"] == "non_html_content"

    def test_discards_page_with_insufficient_main_content(self, tmp_path: Path) -> None:
        pages_path = tmp_path / "pages.jsonl"
        _write_pages_jsonl(
            pages_path, [_base_record(html="<html><body><p>Too short.</p></body></html>")]
        )
        documents_path = tmp_path / "documents.jsonl"
        discarded_path = tmp_path / "discarded.jsonl"

        with ExtractionPipeline(ExtractionConfig(), documents_path, discarded_path) as pipeline:
            stats = pipeline.run(pages_path)

        assert stats.pages_extracted == 0
        assert stats.pages_discarded == 1
        assert stats.discard_counts[DiscardReason.EMPTY_MAIN_CONTENT] == 1

    def test_recovers_mojibake_and_records_encoding_used(self, tmp_path: Path) -> None:
        mojibake_html = _LONG_ARTICLE_HTML.replace(
            "search engines", "café en España — search engines"
        ).encode("utf-8").decode("iso-8859-1")
        pages_path = tmp_path / "pages.jsonl"
        _write_pages_jsonl(
            pages_path,
            [
                _base_record(
                    html=mojibake_html,
                    headers={"Content-Type": "text/html; charset=iso-8859-1"},
                )
            ],
        )
        documents_path = tmp_path / "documents.jsonl"
        discarded_path = tmp_path / "discarded.jsonl"

        with ExtractionPipeline(ExtractionConfig(), documents_path, discarded_path) as pipeline:
            pipeline.run(pages_path)

        document = json.loads(documents_path.read_text(encoding="utf-8").splitlines()[0])
        assert "café en España" in document["main_text"]
        assert document["encoding_used"] == "utf-8"

    def test_one_malformed_page_does_not_abort_the_whole_batch(self, tmp_path: Path) -> None:
        pages_path = tmp_path / "pages.jsonl"
        deeply_broken = "<div>" * 5000 + "<p>unreachable</p>"
        _write_pages_jsonl(
            pages_path,
            [
                _base_record(url="http://example.com/broken", html=deeply_broken),
                _base_record(url="http://example.com/good"),
            ],
        )
        documents_path = tmp_path / "documents.jsonl"
        discarded_path = tmp_path / "discarded.jsonl"

        with ExtractionPipeline(ExtractionConfig(), documents_path, discarded_path) as pipeline:
            stats = pipeline.run(pages_path)

        assert stats.pages_processed == 2
        assert stats.pages_extracted == 1
        assert stats.pages_discarded == 1

        documents = [
            json.loads(line) for line in documents_path.read_text(encoding="utf-8").splitlines()
        ]
        assert documents[0]["url"] == "http://example.com/good"
