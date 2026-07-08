from datetime import UTC, datetime

import pytest

from html_content_extractor.models import (
    DiscardedPage,
    DiscardReason,
    ExtractedDocument,
    ExtractionConfig,
    ExtractionStats,
)


class TestExtractionConfig:
    def test_defaults_are_valid(self) -> None:
        config = ExtractionConfig()
        assert config.min_main_content_chars == 200
        assert config.link_density_threshold == 0.5

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"min_main_content_chars": 0},
            {"min_main_content_chars": -1},
            {"min_block_text_chars": 0},
            {"link_density_threshold": -0.1},
            {"link_density_threshold": 1.1},
        ],
    )
    def test_rejects_invalid_values(self, kwargs: dict[str, object]) -> None:
        with pytest.raises(ValueError):
            ExtractionConfig(**kwargs)  # type: ignore[arg-type]


class TestExtractedDocumentJsonRoundTrip:
    def test_round_trip_preserves_all_fields(self) -> None:
        document = ExtractedDocument(
            url="http://example.com/a",
            final_url="http://example.com/a/",
            title="A title",
            main_text="Some clean body text.",
            language="en",
            author="Jane Doe",
            published_at=datetime(2024, 1, 15, 10, 0, tzinfo=UTC),
            fetched_at=datetime(2024, 1, 15, 9, 0, tzinfo=UTC),
            extracted_at=datetime(2024, 1, 15, 9, 5, tzinfo=UTC),
            encoding_used="utf-8",
            depth=2,
            word_count=4,
        )

        restored = ExtractedDocument.from_json_dict(document.to_json_dict())

        assert restored == document

    def test_round_trip_with_none_optional_fields(self) -> None:
        document = ExtractedDocument(
            url="http://example.com/a",
            final_url="http://example.com/a",
            title="",
            main_text="text",
            language=None,
            author=None,
            published_at=None,
            fetched_at=datetime(2024, 1, 1, tzinfo=UTC),
            extracted_at=datetime(2024, 1, 1, tzinfo=UTC),
            encoding_used="utf-8",
            depth=0,
            word_count=1,
        )

        restored = ExtractedDocument.from_json_dict(document.to_json_dict())

        assert restored == document


class TestDiscardedPage:
    def test_to_json_dict_serializes_reason_as_string_value(self) -> None:
        discarded = DiscardedPage(
            url="http://example.com/x",
            reason=DiscardReason.EMPTY_MAIN_CONTENT,
            detail="no main content",
            discarded_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        data = discarded.to_json_dict()

        assert data["reason"] == "empty_main_content"
        assert data["url"] == "http://example.com/x"


class TestExtractionStats:
    def test_record_extracted_increments_processed_and_extracted(self) -> None:
        stats = ExtractionStats()
        stats.record_extracted()
        stats.record_extracted()

        assert stats.pages_processed == 2
        assert stats.pages_extracted == 2
        assert stats.pages_discarded == 0

    def test_record_discarded_tracks_reason_counts(self) -> None:
        stats = ExtractionStats()
        stats.record_discarded(DiscardReason.PARSE_ERROR)
        stats.record_discarded(DiscardReason.PARSE_ERROR)
        stats.record_discarded(DiscardReason.NON_HTML_CONTENT)

        assert stats.pages_processed == 3
        assert stats.pages_discarded == 3
        assert stats.discard_counts[DiscardReason.PARSE_ERROR] == 2
        assert stats.discard_counts[DiscardReason.NON_HTML_CONTENT] == 1
