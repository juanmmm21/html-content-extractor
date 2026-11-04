"""Huella SimHash de 64 bits para detectar casi-duplicados.

La misma página servida bajo dos URLs, con un pie distinto o una fecha
cambiada, no se detecta comparando hashes exactos del texto. SimHash
(Charikar, 2002; el esquema que describió Google para su crawler en Manku et
al., 2007) produce huellas en las que la distancia de Hamming entre dos
documentos aproxima lo distintos que son: textos casi iguales difieren en muy
pocos bits.

Cálculo:

1. El texto se tokeniza con la misma normalización que `inverted-index-builder`
   (NFC + `casefold` + secuencias de letras/dígitos) y se parte en shingles de
   `shingle_size` palabras consecutivas — con palabras sueltas, dos textos
   con el mismo vocabulario en otro orden darían la misma huella.
2. Cada shingle se hashea a 64 bits con BLAKE2b (determinista entre procesos
   y máquinas, a diferencia de `hash()` de Python, que se aleatoriza).
3. Para cada bit, se suma el peso del shingle (sus apariciones) si el bit
   está a 1 y se resta si está a 0; el bit final de la huella es 1 si la suma
   es positiva.

Búsqueda: con un umbral de `k` bits, la huella se parte en `k + 1` bandas; si
dos huellas difieren en `k` bits o menos, por el principio del palomar al
menos una banda es idéntica. `NearDuplicateIndex` indexa cada banda y solo
compara la distancia completa contra los candidatos que comparten alguna, en
vez de contra todo el corpus.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Final

FINGERPRINT_BITS: Final[int] = 64
DEFAULT_SHINGLE_SIZE: Final[int] = 3
DEFAULT_MAX_DISTANCE: Final[int] = 3
"""Umbral de Manku et al. para huellas de 64 bits sobre páginas web."""

_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"[^\W_]+", re.UNICODE)
_MASK: Final[int] = (1 << FINGERPRINT_BITS) - 1


def _tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFC", text)
    return [
        unicodedata.normalize("NFC", match.group(0).casefold())
        for match in _TOKEN_PATTERN.finditer(normalized)
    ]


def _hash64(feature: str) -> int:
    return int.from_bytes(hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest(), "big")


def simhash64(text: str, *, shingle_size: int = DEFAULT_SHINGLE_SIZE) -> int:
    """Huella de `text`. Un texto sin tokens da 0; uno con menos tokens que
    `shingle_size` usa el texto entero como único shingle."""
    if shingle_size < 1:
        raise ValueError(f"shingle_size debe ser >= 1, recibido {shingle_size}")
    tokens = _tokens(text)
    if not tokens:
        return 0
    if len(tokens) < shingle_size:
        shingles = Counter([" ".join(tokens)])
    else:
        shingles = Counter(
            " ".join(tokens[index : index + shingle_size])
            for index in range(len(tokens) - shingle_size + 1)
        )

    weights = [0] * FINGERPRINT_BITS
    for shingle, count in shingles.items():
        hashed = _hash64(shingle)
        for bit in range(FINGERPRINT_BITS):
            if hashed >> bit & 1:
                weights[bit] += count
            else:
                weights[bit] -= count

    fingerprint = 0
    for bit, weight in enumerate(weights):
        if weight > 0:
            fingerprint |= 1 << bit
    return fingerprint


def hamming_distance(first: int, second: int) -> int:
    return ((first ^ second) & _MASK).bit_count()


def format_fingerprint(fingerprint: int) -> str:
    """16 dígitos hexadecimales en minúscula: el formato de `documents.jsonl`."""
    return f"{fingerprint & _MASK:016x}"


def parse_fingerprint(value: str) -> int:
    if len(value) != 16:
        raise ValueError(f"una huella SimHash tiene 16 dígitos hex, recibido {value!r}")
    return int(value, 16)


@dataclass(frozen=True, slots=True)
class NearDuplicateMatch:
    url: str
    distance: int


class NearDuplicateIndex:
    """Índice en memoria de huellas para encontrar casi-duplicados a distancia
    de Hamming `<= max_distance` sin comparar contra todo el corpus."""

    def __init__(self, max_distance: int = DEFAULT_MAX_DISTANCE) -> None:
        if not 0 <= max_distance < FINGERPRINT_BITS // 2:
            raise ValueError(f"max_distance debe estar en [0, 31], recibido {max_distance}")
        self._max_distance = max_distance
        bands = max_distance + 1
        base, extra = divmod(FINGERPRINT_BITS, bands)
        self._bands: list[tuple[int, int]] = []
        start = 0
        for band in range(bands):
            width = base + (1 if band < extra else 0)
            self._bands.append((start, (1 << width) - 1))
            start += width
        self._tables: list[dict[int, list[tuple[int, str]]]] = [{} for _ in self._bands]
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def _keys(self, fingerprint: int) -> list[int]:
        return [fingerprint >> shift & mask for shift, mask in self._bands]

    def add(self, url: str, fingerprint: int) -> None:
        for table, key in zip(self._tables, self._keys(fingerprint), strict=True):
            table.setdefault(key, []).append((fingerprint, url))
        self._size += 1

    def find(self, fingerprint: int) -> list[NearDuplicateMatch]:
        """Casi-duplicados ya indexados, del más parecido al menos (desempate
        por URL, para que el resultado no dependa del orden de inserción)."""
        best: dict[str, int] = {}
        for table, key in zip(self._tables, self._keys(fingerprint), strict=True):
            for candidate, url in table.get(key, ()):
                distance = hamming_distance(fingerprint, candidate)
                if distance <= self._max_distance and distance < best.get(
                    url, FINGERPRINT_BITS + 1
                ):
                    best[url] = distance
        return [
            NearDuplicateMatch(url=url, distance=distance)
            for url, distance in sorted(best.items(), key=lambda item: (item[1], item[0]))
        ]
