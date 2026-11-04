"""Tipos de datos del dominio para html-content-extractor.

`ExtractedDocument` es inmutable porque es el artefacto final que se
serializa a JSONL y consume `inverted-index-builder`; `DiscardedPage` registra
por qué una página no produjo un documento indexable, para que ninguna URL se
pierda en silencio (ver `../CLAUDE.md`, sección 2.D).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class DiscardReason(StrEnum):
    """Motivo por el que una página crawleada no produjo un documento extraído."""

    DECODE_ERROR = "decode_error"
    PARSE_ERROR = "parse_error"
    NON_HTML_CONTENT = "non_html_content"
    EMPTY_MAIN_CONTENT = "empty_main_content"
    NEAR_DUPLICATE = "near_duplicate"


class NearDuplicateMode(StrEnum):
    """Qué hacer con un documento cuya huella SimHash está a `<= max_distance`
    bits de otro ya extraído (ver `simhash.py`)."""

    OFF = "off"
    """No se calcula huella."""
    ANNOTATE = "annotate"
    """Se emite igualmente, con `near_duplicate_of` apuntando al original."""
    DISCARD = "discard"
    """Se descarta con motivo `near_duplicate`."""


@dataclass(frozen=True, slots=True)
class ExtractionConfig:
    """Configuración del pipeline de extracción y del heurístico de densidad de texto.

    Se valida en `__post_init__` porque una configuración inconsistente
    (p. ej. un umbral de densidad de enlaces fuera de `[0, 1]`) debe fallar de
    forma explícita al construirse, no a mitad de un lote de miles de
    páginas.
    """

    min_main_content_chars: int = 200
    min_block_text_chars: int = 25
    link_density_threshold: float = 0.5
    positive_hint_words: tuple[str, ...] = (
        "article",
        "content",
        "main",
        "body",
        "post",
        "entry",
        "story",
        "text",
    )
    negative_hint_words: tuple[str, ...] = (
        "comment",
        "footer",
        "sidebar",
        "nav",
        "menu",
        "widget",
        "ad",
        "promo",
        "masthead",
        "related",
        "share",
        "social",
        "cookie",
        "banner",
        "popup",
        "subscribe",
        "newsletter",
    )

    near_duplicate_mode: NearDuplicateMode = NearDuplicateMode.ANNOTATE
    near_duplicate_max_distance: int = 3

    def __post_init__(self) -> None:
        if not 0 <= self.near_duplicate_max_distance < 32:
            raise ValueError("near_duplicate_max_distance debe estar en [0, 31]")
        if self.min_main_content_chars <= 0:
            raise ValueError("min_main_content_chars debe ser positivo")
        if self.min_block_text_chars <= 0:
            raise ValueError("min_block_text_chars debe ser positivo")
        if not 0.0 <= self.link_density_threshold <= 1.0:
            raise ValueError("link_density_threshold debe estar entre 0 y 1")


@dataclass(frozen=True, slots=True)
class PageMetadata:
    """Metadatos resueltos a partir del `<head>` y del DOM de una página."""

    title: str
    author: str | None
    published_at: datetime | None
    language: str | None


@dataclass(frozen=True, slots=True)
class MainContentResult:
    """Resultado intermedio de la extracción de contenido principal, antes de normalizar."""

    text: str
    retained_block_count: int


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    """Documento limpio y estructurado, listo para tokenización e indexación."""

    url: str
    final_url: str
    title: str
    main_text: str
    language: str | None
    author: str | None
    published_at: datetime | None
    fetched_at: datetime
    extracted_at: datetime
    encoding_used: str
    depth: int
    word_count: int
    simhash: str | None = None
    """Huella SimHash de 64 bits de `main_text` en 16 dígitos hex (desde 0.2.0)."""
    near_duplicate_of: str | None = None
    """URL del documento ya extraído del que este es casi-duplicado, si lo hay."""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "title": self.title,
            "main_text": self.main_text,
            "language": self.language,
            "author": self.author,
            "published_at": (
                None if self.published_at is None else self.published_at.isoformat()
            ),
            "fetched_at": self.fetched_at.isoformat(),
            "extracted_at": self.extracted_at.isoformat(),
            "encoding_used": self.encoding_used,
            "depth": self.depth,
            "word_count": self.word_count,
            "simhash": self.simhash,
            "near_duplicate_of": self.near_duplicate_of,
        }

    @staticmethod
    def from_json_dict(data: dict[str, Any]) -> ExtractedDocument:
        return ExtractedDocument(
            url=str(data["url"]),
            final_url=str(data["final_url"]),
            title=str(data["title"]),
            main_text=str(data["main_text"]),
            language=None if data["language"] is None else str(data["language"]),
            author=None if data["author"] is None else str(data["author"]),
            published_at=(
                None
                if data["published_at"] is None
                else datetime.fromisoformat(str(data["published_at"]))
            ),
            fetched_at=datetime.fromisoformat(str(data["fetched_at"])),
            extracted_at=datetime.fromisoformat(str(data["extracted_at"])),
            encoding_used=str(data["encoding_used"]),
            depth=int(data["depth"]),
            word_count=int(data["word_count"]),
            # Opcionales: un documents.jsonl anterior a 0.2.0 no los trae.
            simhash=None if data.get("simhash") is None else str(data["simhash"]),
            near_duplicate_of=(
                None if data.get("near_duplicate_of") is None else str(data["near_duplicate_of"])
            ),
        )


@dataclass(frozen=True, slots=True)
class DiscardedPage:
    """Página crawleada que no produjo un documento indexable, conservada para auditoría."""

    url: str
    reason: DiscardReason
    detail: str
    discarded_at: datetime

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "reason": self.reason.value,
            "detail": self.detail,
            "discarded_at": self.discarded_at.isoformat(),
        }


@dataclass(slots=True)
class ExtractionStats:
    """Resumen acumulable de una ejecución de extracción sobre un `pages.jsonl`."""

    pages_processed: int = 0
    pages_extracted: int = 0
    pages_discarded: int = 0
    discard_counts: dict[DiscardReason, int] = field(default_factory=dict)

    def record_extracted(self) -> None:
        self.pages_processed += 1
        self.pages_extracted += 1

    def record_discarded(self, reason: DiscardReason) -> None:
        self.pages_processed += 1
        self.pages_discarded += 1
        self.discard_counts[reason] = self.discard_counts.get(reason, 0) + 1
