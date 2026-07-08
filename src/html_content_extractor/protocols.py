"""Interfaces abstractas que desacoplan `pipeline.py` de las implementaciones concretas de
extracción de contenido principal y metadatos, permitiendo testear cada etapa con dobles de
prueba independientes del DOM real construido por `htmlparse.py`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from html_content_extractor.domtree import DomNode
from html_content_extractor.models import ExtractionConfig, MainContentResult, PageMetadata


@runtime_checkable
class MainContentExtractor(Protocol):
    """Aísla el contenido principal de un documento, descartando boilerplate."""

    def __call__(self, root: DomNode, config: ExtractionConfig) -> MainContentResult: ...


@runtime_checkable
class MetadataExtractor(Protocol):
    """Resuelve título, autor, fecha de publicación e idioma de un documento."""

    def __call__(self, root: DomNode) -> PageMetadata: ...
