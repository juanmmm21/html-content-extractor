"""Heurístico de densidad de texto para separar el contenido principal de una página del
boilerplate (menús, publicidad, pies de página), inspirado en el algoritmo clásico de Arc90
Readability pero reimplementado desde cero y simplificado para este ecosistema.

Idea central: cada bloque de texto "hoja" (un `<p>`, `<li>`, `<td>`, `<pre>`, `<blockquote>`)
recibe una puntuación según su longitud, su puntuación y su densidad de enlaces; esa
puntuación se suma al contenedor padre y, con la mitad de peso, al abuelo, porque la señal
real de "esto es contenido" suele vivir en un contenedor que engloba varios párrafos, no en
el párrafo individual. El contenedor con mayor puntuación acumulada (más el propio indicio de
su `class`/`id`) gana y se usa como raíz del contenido principal; dentro de él se descartan
además los sub-árboles estructuralmente boilerplate y los que tienen mucho texto en enlaces y
poco propio (listas de "artículos relacionados" incrustadas en medio del cuerpo).
"""

from __future__ import annotations

from html_content_extractor.domtree import (
    BLOCK_CANDIDATE_TAGS,
    STRUCTURAL_BOILERPLATE_TAGS,
    DomNode,
)
from html_content_extractor.models import ExtractionConfig, MainContentResult
from html_content_extractor.normalize import collapse_whitespace

_LEAF_TEXT_TAGS = frozenset({"p", "li", "td", "pre", "blockquote"})


def _measure_text_and_link_lengths(node: DomNode, within_link: bool = False) -> tuple[int, int]:
    """Devuelve `(longitud_total_de_texto, longitud_de_texto_dentro_de_enlaces)` del subárbol."""
    within_link = within_link or node.tag == "a"
    own_len = len(collapse_whitespace(node.own_text))
    total = own_len
    link = own_len if within_link else 0
    for child in node.element_children():
        child_total, child_link = _measure_text_and_link_lengths(child, within_link)
        total += child_total
        link += child_link
    return total, link


def _link_density(node: DomNode) -> float:
    total, link = _measure_text_and_link_lengths(node)
    return (link / total) if total > 0 else 1.0


def _class_id_hint_score(node: DomNode, config: ExtractionConfig) -> int:
    haystack = node.class_and_id
    if not haystack.strip():
        return 0
    score = 0
    if any(word in haystack for word in config.positive_hint_words):
        score += 25
    if any(word in haystack for word in config.negative_hint_words):
        score -= 25
    return score


def _leaf_block_score(node: DomNode, config: ExtractionConfig) -> int:
    """Puntúa un bloque de texto hoja según longitud, densidad de comas y clase/id."""
    text = collapse_whitespace(node.text_content())
    if len(text) < config.min_block_text_chars:
        return 0
    score = 1 if node.tag == "p" else 0
    score += text.count(",")
    score += min(len(text) // 100, 3)
    score += _class_id_hint_score(node, config)
    if _link_density(node) > config.link_density_threshold:
        score //= 2  # mucho texto pero mayormente enlaces: sigue siendo sospechoso
    return max(score, 0)


def _score_containers(root: DomNode, config: ExtractionConfig) -> dict[int, int]:
    """Propaga la puntuación de cada bloque hoja a su padre y, con la mitad, a su abuelo."""
    scores: dict[int, int] = {}

    def _add_score(node: DomNode | None, amount: int) -> None:
        if node is None or amount == 0:
            return
        scores[id(node)] = scores.get(id(node), 0) + amount

    def _walk(node: DomNode) -> None:
        if node.tag in _LEAF_TEXT_TAGS:
            leaf_score = _leaf_block_score(node, config)
            if leaf_score > 0:
                parent = node.parent
                _add_score(parent, leaf_score)
                if parent is not None:
                    _add_score(parent.parent, leaf_score // 2)
        for child in node.element_children():
            _walk(child)

    _walk(root)
    return scores


def _best_candidate(
    root: DomNode, scores: dict[int, int], config: ExtractionConfig
) -> DomNode | None:
    best: DomNode | None = None
    best_score = 0
    for node in (root, *root.iter_descendants()):
        if node.tag not in BLOCK_CANDIDATE_TAGS:
            continue
        score = scores.get(id(node), 0) + _class_id_hint_score(node, config)
        if score > best_score:
            best_score = score
            best = node
    return best


def _is_boilerplate_node(node: DomNode, config: ExtractionConfig) -> bool:
    """Un sub-árbol se descarta si es estructuralmente boilerplate (nav/aside/footer/form
    embebido) o si tiene mucho texto en enlaces y poco texto propio (p. ej. un bloque de
    "enlaces relacionados" incrustado en medio del cuerpo del artículo)."""
    if node.tag in STRUCTURAL_BOILERPLATE_TAGS:
        return True
    text = collapse_whitespace(node.text_content())
    if not text:
        return False
    is_link_heavy = _link_density(node) > config.link_density_threshold
    is_short = len(text) < config.min_block_text_chars * 4
    return is_link_heavy and is_short


def _collect_text_parts(node: DomNode, config: ExtractionConfig) -> list[str]:
    """Recorre el subárbol en orden de documento devolviendo un fragmento de texto por bloque
    no descartado como boilerplate; los fragmentos se unen luego con doble salto de línea para
    conservar la separación entre párrafos."""
    if _is_boilerplate_node(node, config):
        return []

    parts: list[str] = []
    text_buffer: list[str] = []
    for child in node.children:
        if isinstance(child, str):
            text_buffer.append(child)
            continue
        if text_buffer:
            buffered = collapse_whitespace("".join(text_buffer))
            if buffered:
                parts.append(buffered)
            text_buffer = []
        parts.extend(_collect_text_parts(child, config))

    if text_buffer:
        buffered = collapse_whitespace("".join(text_buffer))
        if buffered:
            parts.append(buffered)
    return parts


def extract_main_content(root: DomNode, config: ExtractionConfig) -> MainContentResult:
    """Aísla el texto principal de `root`, descartando boilerplate estructural y de enlaces.

    Si ningún contenedor acumula suficiente puntuación (páginas muy cortas, listados, HTML
    atípico) o el texto del ganador queda por debajo del mínimo configurado, se recurre al
    texto completo del documento (ya sin las etiquetas estructuralmente boilerplate), para no
    descartar páginas legítimas pero simples por un heurístico demasiado estricto.
    """
    scores = _score_containers(root, config)
    candidate = _best_candidate(root, scores, config)

    if candidate is not None:
        parts = _collect_text_parts(candidate, config)
        text = "\n\n".join(parts)
        if len(text) >= config.min_main_content_chars:
            return MainContentResult(text=text, retained_block_count=len(parts))

    fallback_parts = _collect_text_parts(root, config)
    fallback_text = "\n\n".join(fallback_parts)
    return MainContentResult(text=fallback_text, retained_block_count=len(fallback_parts))
