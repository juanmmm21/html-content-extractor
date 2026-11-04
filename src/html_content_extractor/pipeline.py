"""Orquestador de la extracción: corrección de encoding -> parseo DOM -> extracción de
contenido principal + metadatos -> normalización -> `ExtractedDocument`.

Cada página se procesa de forma aislada: un anidamiento de HTML excesivamente roto o una
página sin contenido principal suficiente descartan solo esa página (como `DiscardedPage`),
nunca abortan el lote completo (ver `../CLAUDE.md`, sección 2.D).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from html_content_extractor.density import extract_main_content
from html_content_extractor.encoding import resolve_encoding
from html_content_extractor.htmlparse import parse_html
from html_content_extractor.metadata import extract_metadata
from html_content_extractor.models import (
    DiscardedPage,
    DiscardReason,
    ExtractedDocument,
    ExtractionConfig,
    ExtractionStats,
    NearDuplicateMode,
)
from html_content_extractor.normalize import normalize_text
from html_content_extractor.simhash import (
    NearDuplicateIndex,
    format_fingerprint,
    parse_fingerprint,
    simhash64,
)

logger = logging.getLogger(__name__)

# Prefijos de `Content-Type` que nunca son HTML navegable: se descartan antes de intentar
# parsear, en vez de dejar que el parser produzca un árbol vacío o con ruido binario.
_NON_HTML_CONTENT_TYPE_PREFIXES = (
    "image/",
    "audio/",
    "video/",
    "application/pdf",
    "application/zip",
    "application/octet-stream",
)


class ExtractionPipeline:
    """Convierte un `pages.jsonl` de `web-crawler-scheduler` en `documents.jsonl` +
    `discarded.jsonl`.

    Se usa como *context manager* para garantizar que ambos ficheros de salida se cierran
    explícitamente incluso si el lote se interrumpe a mitad:

        with ExtractionPipeline(config, documents_path, discarded_path) as pipeline:
            stats = pipeline.run(pages_path)
    """

    def __init__(
        self,
        config: ExtractionConfig,
        documents_output_path: Path,
        discarded_output_path: Path,
    ) -> None:
        self._config = config
        self._documents_output_path = documents_output_path
        self._discarded_output_path = discarded_output_path
        self._documents_file: TextIO | None = None
        self._discarded_file: TextIO | None = None
        self._stats = ExtractionStats()
        self._near_duplicates = NearDuplicateIndex(config.near_duplicate_max_distance)

    def __enter__(self) -> ExtractionPipeline:
        self._documents_output_path.parent.mkdir(parents=True, exist_ok=True)
        self._discarded_output_path.parent.mkdir(parents=True, exist_ok=True)
        self._documents_file = self._documents_output_path.open("a", encoding="utf-8")
        self._discarded_file = self._discarded_output_path.open("a", encoding="utf-8")
        return self

    def __exit__(self, *_exc_info: object) -> None:
        for handle in (self._documents_file, self._discarded_file):
            if handle is not None:
                handle.close()
        self._documents_file = None
        self._discarded_file = None

    def prime_near_duplicates(self, documents_path: Path) -> int:
        """Carga las huellas de un `documents.jsonl` ya extraído, para que una
        extracción incremental detecte casi-duplicados contra el corpus
        existente y no solo dentro del lote. Los documentos sin huella
        (anteriores a 0.2.0) se huellan aquí. Devuelve cuántos se cargaron."""
        if self._config.near_duplicate_mode is NearDuplicateMode.OFF:
            return 0
        loaded = 0
        with documents_path.open("r", encoding="utf-8") as documents_file:
            for raw_line in documents_file:
                if not raw_line.strip():
                    continue
                document = ExtractedDocument.from_json_dict(json.loads(raw_line))
                fingerprint = (
                    parse_fingerprint(document.simhash)
                    if document.simhash is not None
                    else simhash64(document.main_text)
                )
                self._near_duplicates.add(document.url, fingerprint)
                loaded += 1
        return loaded

    def run(self, pages_path: Path) -> ExtractionStats:
        with pages_path.open("r", encoding="utf-8") as pages_file:
            for raw_line in pages_file:
                line = raw_line.strip()
                if not line:
                    continue
                self._process_record(json.loads(line))
        return self._stats

    def _resolve_content_type_header(self, record: dict[str, Any]) -> str | None:
        headers = record.get("headers")
        if isinstance(headers, dict):
            for key, value in headers.items():
                if str(key).lower() == "content-type":
                    return str(value)
        content_type = record.get("content_type")
        return str(content_type) if isinstance(content_type, str) else None

    def _process_record(self, record: dict[str, Any]) -> None:
        url = str(record["url"])
        final_url = str(record["final_url"])
        html = str(record["html"])
        depth = int(record.get("depth", 0))
        fetched_at = datetime.fromisoformat(str(record["fetched_at"]))

        content_type_header = self._resolve_content_type_header(record)
        if content_type_header is not None:
            mime_type = content_type_header.split(";")[0].strip().lower()
            if mime_type.startswith(_NON_HTML_CONTENT_TYPE_PREFIXES):
                self._discard(url, DiscardReason.NON_HTML_CONTENT, content_type_header)
                return

        resolved_html, encoding_used = resolve_encoding(html, content_type_header)

        try:
            root = parse_html(resolved_html)
            main_content = extract_main_content(root, self._config)
        except RecursionError as exc:
            logger.warning("Anidamiento de HTML excesivo en %s", url)
            self._discard(url, DiscardReason.PARSE_ERROR, f"recursión excesiva: {exc}")
            return

        if len(main_content.text) < self._config.min_main_content_chars:
            self._discard(
                url,
                DiscardReason.EMPTY_MAIN_CONTENT,
                "contenido principal insuficiente tras el heurístico de densidad",
            )
            return

        metadata = extract_metadata(root)
        normalized_text = normalize_text(main_content.text)

        fingerprint: int | None = None
        near_duplicate_of: str | None = None
        if self._config.near_duplicate_mode is not NearDuplicateMode.OFF:
            fingerprint = simhash64(normalized_text)
            # Una versión nueva de la misma URL no es un duplicado de sí misma.
            matches = [m for m in self._near_duplicates.find(fingerprint) if m.url != url]
            if matches:
                near_duplicate_of = matches[0].url
                if self._config.near_duplicate_mode is NearDuplicateMode.DISCARD:
                    self._discard(
                        url,
                        DiscardReason.NEAR_DUPLICATE,
                        f"casi-duplicado de {matches[0].url} "
                        f"(distancia de Hamming {matches[0].distance})",
                    )
                    return

        document = ExtractedDocument(
            url=url,
            final_url=final_url,
            title=metadata.title,
            main_text=normalized_text,
            language=metadata.language,
            author=metadata.author,
            published_at=metadata.published_at,
            fetched_at=fetched_at,
            extracted_at=datetime.now(UTC),
            encoding_used=encoding_used,
            depth=depth,
            word_count=len(normalized_text.split()),
            simhash=format_fingerprint(fingerprint) if fingerprint is not None else None,
            near_duplicate_of=near_duplicate_of,
        )
        if fingerprint is not None:
            self._near_duplicates.add(url, fingerprint)
        self._write_document(document)
        self._stats.record_extracted()

    def _discard(self, url: str, reason: DiscardReason, detail: str) -> None:
        assert self._discarded_file is not None, "usar ExtractionPipeline dentro de 'with'"
        discarded = DiscardedPage(
            url=url, reason=reason, detail=detail, discarded_at=datetime.now(UTC)
        )
        self._discarded_file.write(json.dumps(discarded.to_json_dict(), ensure_ascii=False) + "\n")
        self._discarded_file.flush()
        self._stats.record_discarded(reason)

    def _write_document(self, document: ExtractedDocument) -> None:
        assert self._documents_file is not None, "usar ExtractionPipeline dentro de 'with'"
        self._documents_file.write(json.dumps(document.to_json_dict(), ensure_ascii=False) + "\n")
        self._documents_file.flush()
