"""CLI de `html-content-extractor`: `extract` (procesa un `pages.jsonl`) y `stats`."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from html_content_extractor.models import ExtractionConfig
from html_content_extractor.pipeline import ExtractionPipeline

logger = logging.getLogger("html_content_extractor")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="html-content-extractor",
        description="Extractor de contenido principal limpio a partir de HTML crawleado.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser(
        "extract", help="Extrae contenido principal de un pages.jsonl"
    )
    extract_parser.add_argument(
        "pages_path", type=Path, help="pages.jsonl producido por web-crawler-scheduler"
    )
    extract_parser.add_argument("--output-dir", type=Path, required=True)
    extract_parser.add_argument("--min-main-content-chars", type=int, default=200)
    extract_parser.add_argument("--min-block-text-chars", type=int, default=25)
    extract_parser.add_argument("--link-density-threshold", type=float, default=0.5)

    stats_parser = subparsers.add_parser(
        "stats", help="Muestra estadísticas de un documents.jsonl"
    )
    stats_parser.add_argument("documents_path", type=Path)

    return parser


def _run_extract(args: argparse.Namespace) -> int:
    pages_path: Path = args.pages_path
    if not pages_path.exists():
        print(f"Error: no existe {pages_path}", file=sys.stderr)
        return 2

    config = ExtractionConfig(
        min_main_content_chars=args.min_main_content_chars,
        min_block_text_chars=args.min_block_text_chars,
        link_density_threshold=args.link_density_threshold,
    )

    output_dir: Path = args.output_dir
    with ExtractionPipeline(
        config,
        output_dir / "documents.jsonl",
        output_dir / "discarded.jsonl",
    ) as pipeline:
        stats = pipeline.run(pages_path)

    print(
        f"Extracción finalizada: {stats.pages_extracted} documentos, "
        f"{stats.pages_discarded} descartados (de {stats.pages_processed} procesados)"
    )
    for reason, count in sorted(stats.discard_counts.items(), key=lambda item: item[0].value):
        print(f"  {reason.value}: {count}")
    return 0


def _run_stats(args: argparse.Namespace) -> int:
    documents_path: Path = args.documents_path
    if not documents_path.exists():
        print(f"Error: no existe {documents_path}", file=sys.stderr)
        return 2

    total = 0
    total_words = 0
    languages: dict[str, int] = {}
    for line in documents_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        total += 1
        total_words += int(record["word_count"])
        language = record.get("language") or "desconocido"
        languages[language] = languages.get(language, 0) + 1

    print(f"Documentos: {total}")
    if total > 0:
        print(f"Palabras medias por documento: {total_words / total:.0f}")
    for language in sorted(languages):
        print(f"  {language}: {languages[language]}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "extract":
        return _run_extract(args)
    if args.command == "stats":
        return _run_stats(args)

    parser.error(f"Comando desconocido: {args.command}")
    return 2  # inalcanzable: parser.error() termina el proceso con sys.exit()


if __name__ == "__main__":
    sys.exit(main())
