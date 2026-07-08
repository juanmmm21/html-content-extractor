"""Construcción de un `DomNode` a partir de HTML crudo, usando `html.parser.HTMLParser` de la
librería estándar en vez de una librería de parsing de terceros: igual que en
`web-crawler-scheduler/link_extractor.py`, `HTMLParser` tolera de forma nativa etiquetas sin
cerrar y anidamiento inválido, sin depender de `lxml` ni `selectolax`.

El HTML real llega roto (tags sin cerrar, cierres huérfanos, anidamiento inconsistente); esta
capa aplica una versión simplificada de las reglas de recuperación de un navegador real:
- Una etiqueta de cierre sin apertura correspondiente en la pila se ignora, no aborta el parseo.
- Ciertas etiquetas de bloque cierran implícitamente un `<p>` todavía abierto (regla HTML5
  real: un `<p>` nunca puede contener un elemento de bloque; los navegadores lo cierran solos).
"""

from __future__ import annotations

from html.parser import HTMLParser

from html_content_extractor.domtree import SKIPPED_TAGS, VOID_TAGS, DomNode

_IMPLICIT_P_CLOSERS = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "div",
        "dl",
        "fieldset",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "main",
        "menu",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "ul",
    }
)


class _TreeBuildingParser(HTMLParser):
    """Construye un `DomNode` raíz mientras alimenta el HTML crudo al parser."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = DomNode(tag="#root")
        self._stack: list[DomNode] = [self.root]
        self._skip_depth = 0  # >0 mientras estamos dentro de un tag de SKIPPED_TAGS anidado

    @property
    def _current(self) -> DomNode:
        return self._stack[-1]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open_tag(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._open_tag(tag, attrs, self_closing=True)

    def _open_tag(
        self, tag: str, attrs: list[tuple[str, str | None]], *, self_closing: bool
    ) -> None:
        tag_lower = tag.lower()

        if self._skip_depth > 0:
            if tag_lower in SKIPPED_TAGS:
                self._skip_depth += 1
            return

        if tag_lower in _IMPLICIT_P_CLOSERS and self._current.tag == "p":
            self._stack.pop()

        node = DomNode(
            tag=tag_lower,
            attrs={name.lower(): (value or "") for name, value in attrs},
            parent=self._current,
        )
        self._current.children.append(node)

        if tag_lower in SKIPPED_TAGS:
            self._skip_depth = 1
            return
        if not self_closing and tag_lower not in VOID_TAGS:
            self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()

        if self._skip_depth > 0:
            if tag_lower in SKIPPED_TAGS:
                self._skip_depth -= 1
            return
        if tag_lower in VOID_TAGS:
            return  # cierre huérfano de un void element (p. ej. `</br>`): nada que cerrar

        # Busca el tag correspondiente en la pila de ancestros abiertos, ignorando cierres
        # huérfanos que no abren nada — la misma recuperación que aplica un navegador real.
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag_lower:
                del self._stack[index:]
                return
        # Sin match: cierre huérfano, se ignora explícitamente en vez de abortar el parseo.

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0 or not data:
            return
        self._current.children.append(data)


def parse_html(html_text: str) -> DomNode:
    """Parsea `html_text` (ya decodificado) en un `DomNode` raíz tolerante a HTML malformado."""
    parser = _TreeBuildingParser()
    parser.feed(html_text)
    parser.close()
    return parser.root
