"""Normalización de texto: colapso de espacios en blanco y forma Unicode NFC, antes de que el
texto extraído llegue a `inverted-index-builder` para tokenización.
"""

from __future__ import annotations

import re
import unicodedata

_INLINE_WHITESPACE_RE = re.compile(r"[ \t\f\v]+")
_EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")


def collapse_whitespace(text: str) -> str:
    """Colapsa espacios/tabs repetidos a uno solo y recorta los bordes; conserva saltos de línea."""
    return _INLINE_WHITESPACE_RE.sub(" ", text).strip()


def normalize_text(text: str) -> str:
    """Normaliza NFC y limpia el texto extraído antes de pasarlo a indexación.

    Se usa NFC (no NFKC/NFKD) porque solo se quiere unificar formas equivalentes (p. ej. una
    "é" compuesta de dos codepoints frente a la precompuesta), sin destruir distinciones
    tipográficas reales que sí importan para tokenización: NFKC normalizaría también
    ligaduras y variantes de ancho de caracteres, alterando el vocabulario indexado de forma
    no deseada.
    """
    normalized = unicodedata.normalize("NFC", text)
    collapsed = collapse_whitespace(normalized)
    return _EXCESS_BLANK_LINES_RE.sub("\n\n", collapsed)
