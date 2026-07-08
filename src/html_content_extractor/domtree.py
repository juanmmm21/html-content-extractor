"""Árbol DOM minimalista construido a mano: solo lo que necesita el heurístico de densidad
de texto (etiqueta, atributos, texto y elementos hijos en orden de documento).

No se usa un DOM completo tipo `xml.dom.minidom` porque no se necesita el grueso de su API
(namespaces, manipulación, serialización); un árbol propio y más simple es más fácil de
razonar y de testear que envolver una librería general con una interfaz mucho más amplia
de la que realmente se usa aquí.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

# Etiquetas cuyo contenido nunca es texto de la página (script/estilo/comentarios embebidos):
# se descartan por completo durante el parseo (ver `htmlparse.py`), nunca llegan a formar
# parte del árbol, porque no deben contar ni como candidatos a contenido principal ni
# contaminar el texto agregado de ningún ancestro.
SKIPPED_TAGS = frozenset({"script", "style", "noscript", "template", "svg", "iframe"})

# Etiquetas estructuralmente boilerplate por definición (navegación, cabecera, pie, formularios).
# A diferencia de `SKIPPED_TAGS`, estas sí permanecen en el árbol (aportan señal de qué NO es
# contenido principal) y se filtran explícitamente al recolectar texto en `density.py`.
STRUCTURAL_BOILERPLATE_TAGS = frozenset({"nav", "header", "footer", "aside", "form"})

# Elementos "vacíos" (void elements) de HTML5: nunca tienen etiqueta de cierre y por tanto
# nunca deben empujarse a la pila de ancestros abiertos al parsear.
VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)

# Elementos de bloque considerados candidatos a contenedor de contenido principal.
BLOCK_CANDIDATE_TAGS = frozenset({"div", "section", "article", "main", "td", "body"})


@dataclass(slots=True)
class DomNode:
    """Un nodo de elemento del árbol.

    `children` mezcla nodos de texto (`str`) y elementos (`DomNode`) en el mismo orden en
    que aparecen en el documento: separar el texto en una lista propia perdería el orden
    relativo entre texto y sub-elementos (p. ej. "antes <b>negrita</b> después"), que sí
    importa para reconstruir el texto principal de forma fiel.
    """

    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[DomNode | str] = field(default_factory=list)
    parent: DomNode | None = field(default=None, repr=False, compare=False)

    @property
    def own_text(self) -> str:
        """Texto que cuelga directamente de este nodo (no de sus hijos-elemento)."""
        return "".join(child for child in self.children if isinstance(child, str))

    @property
    def class_and_id(self) -> str:
        return f"{self.attrs.get('class', '')} {self.attrs.get('id', '')}".lower()

    def element_children(self) -> list[DomNode]:
        return [child for child in self.children if isinstance(child, DomNode)]

    def iter_descendants(self) -> Iterator[DomNode]:
        for child in self.element_children():
            yield child
            yield from child.iter_descendants()

    def text_content(self) -> str:
        """Todo el texto del subárbol, concatenado en orden de documento."""
        parts: list[str] = []
        for child in self.children:
            if isinstance(child, str):
                if child:
                    parts.append(child)
            else:
                child_text = child.text_content()
                if child_text:
                    parts.append(child_text)
        return "".join(parts)

    def find_first(self, tag: str) -> DomNode | None:
        """Busca en profundidad (pre-order) el primer descendiente con esa etiqueta."""
        for descendant in self.iter_descendants():
            if descendant.tag == tag:
                return descendant
        return None

    def find_all(self, *tags: str) -> list[DomNode]:
        wanted = frozenset(tags)
        return [descendant for descendant in self.iter_descendants() if descendant.tag in wanted]
