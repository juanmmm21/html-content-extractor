"""Extracción de título, autor, fecha de publicación e idioma a partir del `<head>` y del DOM.

Prioriza siempre la señal más explícita disponible (meta tags dedicados) sobre heurísticas
más débiles (primer `<h1>`, atributo `lang` del `<html>`): una etiqueta `<meta>` bien formada
es una declaración explícita del propio sitio, mientras que el resto son suposiciones
razonables solo cuando esa declaración no existe.
"""

from __future__ import annotations

from datetime import datetime

from html_content_extractor.domtree import DomNode
from html_content_extractor.models import PageMetadata
from html_content_extractor.normalize import collapse_whitespace


def _meta_content(root: DomNode, attr: str, value: str) -> str | None:
    """Busca un `<meta>` cuyo atributo `attr` (`name`/`property`/`http-equiv`) coincida con
    `value` (sin distinguir mayúsculas) y devuelve su `content`, o `None` si no hay ninguno
    con texto no vacío."""
    for meta in root.find_all("meta"):
        if meta.attrs.get(attr, "").lower() == value.lower():
            content = meta.attrs.get("content", "").strip()
            if content:
                return content
    return None


def _extract_title(root: DomNode) -> str:
    og_title = _meta_content(root, "property", "og:title")
    if og_title:
        return og_title

    heading = root.find_first("h1")
    if heading is not None:
        heading_text = collapse_whitespace(heading.text_content())
        if heading_text:
            return heading_text

    title_tag = root.find_first("title")
    if title_tag is not None:
        return collapse_whitespace(title_tag.text_content())
    return ""


def _extract_author(root: DomNode) -> str | None:
    return (
        _meta_content(root, "name", "author")
        or _meta_content(root, "property", "article:author")
        or _meta_content(root, "name", "twitter:creator")
    )


def _parse_datetime(raw: str) -> datetime | None:
    try:
        return datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_published_at(root: DomNode) -> datetime | None:
    raw = (
        _meta_content(root, "property", "article:published_time")
        or _meta_content(root, "name", "date")
        or _meta_content(root, "name", "pubdate")
    )
    if raw is None:
        time_tag = root.find_first("time")
        if time_tag is not None:
            raw = time_tag.attrs.get("datetime", "").strip() or collapse_whitespace(
                time_tag.text_content()
            )
    if not raw:
        return None
    return _parse_datetime(raw)


def _extract_language(root: DomNode) -> str | None:
    html_tag = root.find_first("html")
    if html_tag is not None:
        lang = html_tag.attrs.get("lang", "").strip()
        if lang:
            return lang

    content_language = _meta_content(root, "http-equiv", "content-language")
    if content_language:
        return content_language.split(",")[0].strip()
    return None


def extract_metadata(root: DomNode) -> PageMetadata:
    """Resuelve los metadatos de una página ya parseada en `DomNode`."""
    return PageMetadata(
        title=_extract_title(root),
        author=_extract_author(root),
        published_at=_extract_published_at(root),
        language=_extract_language(root),
    )
