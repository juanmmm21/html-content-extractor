"""Corrección de encoding para HTML ya decodificado a `str` por `web-crawler-scheduler`.

El crawler entrega `PageRecord.html` como texto ya decodificado (vía la propia detección de
encoding de `aiohttp`, que usa el charset declarado en la cabecera HTTP `Content-Type` si
existe, o `utf-8` por defecto en caso contrario). Esa decodificación puede ser incorrecta
cuando el charset real de los bytes originales no coincide con el que declaró la cabecera
— algo frecuente cuando el servidor mal configura su charset pero el propio HTML declara el
correcto en un `<meta charset>` — produciendo mojibake (p. ej. "cafÃ©" en vez de "café"). Esta
capa detecta esa discrepancia mediante marcadores típicos de mojibake y, si aparecen, intenta
una re-decodificación correctiva: rehace el texto a bytes con el encoding que probablemente
usó `aiohttp` y lo vuelve a decodificar con cada encoding candidato (el declarado en el
`<meta>` si discrepa, y si no, el par utf-8/windows-1252, la confusión más común en la
práctica), aceptando el primero que reduzca de forma objetiva la cantidad de marcadores.
"""

from __future__ import annotations

import re

_CONTENT_TYPE_CHARSET_RE = re.compile(r"charset=([\w.:-]+)", re.IGNORECASE)
_META_CHARSET_RE = re.compile(r'<meta[^>]+charset=["\']?\s*([\w.:-]+)', re.IGNORECASE)
_META_HTTP_EQUIV_CHARSET_RE = re.compile(
    r'<meta[^>]+http-equiv=["\']content-type["\'][^>]+content=["\'][^"\']*charset=([\w.:-]+)',
    re.IGNORECASE,
)

# Secuencias que solo aparecen cuando un byte UTF-8 multibyte se reinterpretó byte a byte
# como un encoding de un solo byte (Latin-1/Windows-1252), o cuando el decodificador tuvo que
# sustituir un byte no decodificable por el carácter de reemplazo Unicode.
_MOJIBAKE_MARKERS = ("Ã", "Â", "â€", "\ufffd")

# Confusión de encoding más común en la práctica cuando no hay un <meta charset> que la
# desmienta: contenido real en utf-8 servido/declarado como si fuera de un solo byte, o al
# revés. Se prueban ambos sentidos como último recurso heurístico.
_COMMON_FALLBACK_CHARSETS = ("utf-8", "windows-1252")


def _extract_declared_charset(html_prefix: str) -> str | None:
    """Busca el charset declarado en un `<meta>` dentro de los primeros bytes del documento."""
    match = _META_HTTP_EQUIV_CHARSET_RE.search(html_prefix) or _META_CHARSET_RE.search(
        html_prefix
    )
    return match.group(1).strip().lower() if match else None


def _extract_header_charset(content_type_header: str | None) -> str | None:
    if not content_type_header:
        return None
    match = _CONTENT_TYPE_CHARSET_RE.search(content_type_header)
    return match.group(1).strip().lower() if match else None


def _count_mojibake_markers(text: str) -> int:
    return sum(text.count(marker) for marker in _MOJIBAKE_MARKERS)


def _try_redecode(text: str, assumed_encoding: str, declared_encoding: str) -> str | None:
    """Reinterpreta `text` como si se hubiera decodificado con el encoding equivocado.

    Cualquier fallo de la operación completa (encode + decode) o un nombre de encoding
    desconocido se captura explícitamente: es una corrección best-effort de la que el
    pipeline nunca depende para poder continuar.
    """
    try:
        raw_bytes = text.encode(assumed_encoding, errors="strict")
        return raw_bytes.decode(declared_encoding, errors="strict")
    except (UnicodeEncodeError, UnicodeDecodeError, LookupError):
        return None


def _candidate_charsets(assumed_encoding: str, meta_charset: str | None) -> list[str]:
    """Ordena los encodings a probar: primero el declarado en el `<meta>` si discrepa del
    asumido (es la señal más explícita), después la confusión utf-8/windows-1252 clásica."""
    candidates: list[str] = []
    if meta_charset and meta_charset != assumed_encoding:
        candidates.append(meta_charset)
    for fallback in _COMMON_FALLBACK_CHARSETS:
        if fallback != assumed_encoding and fallback not in candidates:
            candidates.append(fallback)
    return candidates


def resolve_encoding(html_text: str, content_type_header: str | None) -> tuple[str, str]:
    """Devuelve `(texto_final, encoding_usado)`.

    `assumed_encoding` (el encoding que probablemente usó `aiohttp` para producir `html_text`)
    se infiere del charset de la cabecera `Content-Type` si está declarado, o `utf-8` si no.
    Solo se intenta corregir si hay marcadores de mojibake; se prueba cada candidato en orden
    y se acepta el primero cuya re-decodificación reduzca objetivamente el número de
    marcadores. En cualquier otro caso se devuelve el texto de entrada sin modificar junto con
    el encoding asumido: esta función nunca lanza.
    """
    header_charset = _extract_header_charset(content_type_header)
    meta_charset = _extract_declared_charset(html_text[:2048])
    assumed_encoding = header_charset or "utf-8"

    marker_count = _count_mojibake_markers(html_text)
    if marker_count == 0:
        return html_text, assumed_encoding

    for declared_charset in _candidate_charsets(assumed_encoding, meta_charset):
        corrected = _try_redecode(html_text, assumed_encoding, declared_charset)
        if corrected is not None and _count_mojibake_markers(corrected) < marker_count:
            return corrected, declared_charset

    return html_text, assumed_encoding
