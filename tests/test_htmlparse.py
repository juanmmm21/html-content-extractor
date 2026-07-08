from html_content_extractor.htmlparse import parse_html


class TestWellFormedHtml:
    def test_parses_nested_structure_and_text(self) -> None:
        root = parse_html("<html><body><div><p>Hello world</p></div></body></html>")

        paragraph = root.find_first("p")
        assert paragraph is not None
        assert paragraph.text_content() == "Hello world"

    def test_parses_attributes_lowercased(self) -> None:
        root = parse_html('<div CLASS="Article" id="Main">text</div>')

        div = root.find_first("div")
        assert div is not None
        assert div.attrs == {"class": "Article", "id": "Main"}

    def test_void_elements_never_open_a_scope(self) -> None:
        root = parse_html("<div>before<br>after<img src='x.png'>tail</div>")

        div = root.find_first("div")
        assert div is not None
        assert div.text_content() == "beforeaftertail"
        assert div.find_first("br") is not None
        assert div.find_first("img") is not None

    def test_self_closing_tag_is_treated_as_void(self) -> None:
        root = parse_html('<div><hr/><p>after</p></div>')

        div = root.find_first("div")
        assert div is not None
        assert [child.tag for child in div.element_children()] == ["hr", "p"]

    def test_entities_are_decoded(self) -> None:
        root = parse_html("<p>Tom &amp; Jerry &lt;3&gt;</p>")

        paragraph = root.find_first("p")
        assert paragraph is not None
        assert paragraph.text_content() == "Tom & Jerry <3>"


class TestSkippedTags:
    def test_script_content_is_never_added_to_the_tree(self) -> None:
        root = parse_html("<body><script>var x = '<p>fake</p>';</script><p>real</p></body>")

        assert root.find_first("script") is None
        paragraphs = root.find_all("p")
        assert [p.text_content() for p in paragraphs] == ["real"]

    def test_nested_script_like_tags_do_not_leak_text(self) -> None:
        root = parse_html("<style>.a { color: red; }</style><p>visible</p>")

        assert root.find_first("style") is None
        paragraph = root.find_first("p")
        assert paragraph is not None
        assert paragraph.text_content() == "visible"


class TestMalformedHtmlTolerance:
    def test_unclosed_paragraph_is_implicitly_closed_by_next_block(self) -> None:
        root = parse_html("<div><p>First paragraph<p>Second paragraph</div>")

        div = root.find_first("div")
        assert div is not None
        paragraphs = div.element_children()
        assert [p.tag for p in paragraphs] == ["p", "p"]
        assert paragraphs[0].text_content() == "First paragraph"
        assert paragraphs[1].text_content() == "Second paragraph"

    def test_orphan_closing_tag_is_ignored_without_aborting_parse(self) -> None:
        root = parse_html("<div>before</span><p>still parsed</p></div>")

        div = root.find_first("div")
        assert div is not None
        paragraph = div.find_first("p")
        assert paragraph is not None
        assert paragraph.text_content() == "still parsed"

    def test_heading_implicitly_closes_open_paragraph(self) -> None:
        root = parse_html("<div><p>paragraph text<h2>heading text</h2></div>")

        div = root.find_first("div")
        assert div is not None
        assert [child.tag for child in div.element_children()] == ["p", "h2"]

    def test_deeply_unbalanced_document_does_not_raise(self) -> None:
        broken = "<div>" * 50 + "<p>content</p>"
        root = parse_html(broken)

        paragraph = root.find_first("p")
        assert paragraph is not None
        assert paragraph.text_content() == "content"
