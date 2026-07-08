from html_content_extractor.domtree import DomNode


def _build_sample_tree() -> DomNode:
    root = DomNode(tag="#root")
    body = DomNode(tag="body", parent=root)
    root.children.append(body)

    div = DomNode(tag="div", attrs={"class": "content"}, parent=body)
    body.children.append(div)

    paragraph = DomNode(tag="p", parent=div)
    div.children.append(paragraph)
    paragraph.children.append("before ")
    bold = DomNode(tag="b", parent=paragraph)
    paragraph.children.append(bold)
    bold.children.append("bold")
    paragraph.children.append(" after")

    return root


class TestDomNode:
    def test_own_text_only_includes_direct_text(self) -> None:
        root = _build_sample_tree()
        paragraph = root.find_first("p")

        assert paragraph is not None
        assert paragraph.own_text == "before  after"

    def test_text_content_preserves_document_order_across_children(self) -> None:
        root = _build_sample_tree()
        paragraph = root.find_first("p")

        assert paragraph is not None
        assert paragraph.text_content() == "before bold after"

    def test_class_and_id_combines_both_attributes_lowercased(self) -> None:
        node = DomNode(tag="div", attrs={"class": "Article-Body", "id": "MAIN"})

        assert node.class_and_id == "article-body main"

    def test_find_first_returns_none_when_missing(self) -> None:
        root = _build_sample_tree()

        assert root.find_first("table") is None

    def test_find_all_collects_every_matching_descendant_in_order(self) -> None:
        root = DomNode(tag="#root")
        body = DomNode(tag="body", parent=root)
        root.children.append(body)
        for text in ("first", "second", "third"):
            p = DomNode(tag="p", parent=body)
            p.children.append(text)
            body.children.append(p)

        paragraphs = root.find_all("p")

        assert [p.own_text for p in paragraphs] == ["first", "second", "third"]

    def test_iter_descendants_yields_only_elements_not_text_nodes(self) -> None:
        root = _build_sample_tree()

        tags = [node.tag for node in root.iter_descendants()]

        assert tags == ["body", "div", "p", "b"]
