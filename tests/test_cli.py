import json
from pathlib import Path

import pytest

from html_content_extractor.__main__ import _build_parser, _run_extract, _run_stats


class TestArgumentParsing:
    def test_extract_requires_output_dir(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["extract", "pages.jsonl"])

    def test_extract_parses_defaults(self, tmp_path: Path) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            ["extract", "pages.jsonl", "--output-dir", str(tmp_path)]
        )

        assert args.command == "extract"
        assert args.min_main_content_chars == 200
        assert args.link_density_threshold == 0.5

    def test_stats_requires_documents_path(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["stats"])

    def test_unknown_command_exits(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["bogus"])


class TestRunExtract:
    def test_reports_missing_pages_file(self, tmp_path: Path) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            ["extract", str(tmp_path / "missing.jsonl"), "--output-dir", str(tmp_path)]
        )

        assert _run_extract(args) == 2

    def test_extracts_and_prints_summary(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        pages_path = tmp_path / "pages.jsonl"
        record = {
            "url": "http://example.com/a",
            "final_url": "http://example.com/a",
            "status_code": 200,
            "headers": {"Content-Type": "text/html; charset=utf-8"},
            "html": (
                "<html><body><article><h1>Title</h1>"
                "<p>A real paragraph with enough substantial text content to pass the "
                "minimum main content length threshold configured for this extractor.</p>"
                "<p>A second paragraph adding even more genuine prose so the density "
                "heuristic confidently keeps this article as the winning candidate.</p>"
                "</article></body></html>"
            ),
            "fetched_at": "2024-01-01T00:00:00+00:00",
            "depth": 0,
            "content_type": "text/html",
        }
        pages_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        output_dir = tmp_path / "out"
        parser = _build_parser()
        args = parser.parse_args(
            ["extract", str(pages_path), "--output-dir", str(output_dir)]
        )

        exit_code = _run_extract(args)

        assert exit_code == 0
        output = capsys.readouterr().out
        assert "1 documentos" in output
        assert (output_dir / "documents.jsonl").exists()


class TestRunStats:
    def test_reports_missing_file(self, tmp_path: Path) -> None:
        parser = _build_parser()
        args = parser.parse_args(["stats", str(tmp_path / "missing.jsonl")])

        assert _run_stats(args) == 2

    def test_summarizes_documents_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        documents_path = tmp_path / "documents.jsonl"
        records = [
            {"word_count": 100, "language": "en"},
            {"word_count": 200, "language": "en"},
            {"word_count": 50, "language": "es"},
        ]
        documents_path.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
        )
        parser = _build_parser()
        args = parser.parse_args(["stats", str(documents_path)])

        exit_code = _run_stats(args)

        assert exit_code == 0
        output = capsys.readouterr().out
        assert "Documentos: 3" in output
        assert "en: 2" in output
        assert "es: 1" in output
