from html_content_extractor.density import extract_main_content
from html_content_extractor.htmlparse import parse_html
from html_content_extractor.models import ExtractionConfig

_ARTICLE_HTML = """
<html><body>
<header><nav><a href="/">Home</a><a href="/about">About</a>
<a href="/contact">Contact</a></nav></header>
<div class="sidebar">
<ul>
<li><a href="/x">Related article one</a></li>
<li><a href="/y">Related article two</a></li>
<li><a href="/z">Related article three</a></li>
</ul>
</div>
<article class="post-content">
<h1>A Genuinely Long Article Title</h1>
<p>This is the first paragraph of a real article about search engines, covering how
inverted indexes are built from scratch, why tokenization matters, and how relevance
scoring eventually combines several independent signals into one ranked list.</p>
<p>This second paragraph goes deeper into implementation details, discussing positional
postings, document frequency statistics, and the trade-offs of different compression
schemes used to keep the index small enough to fit comfortably in memory.</p>
<div class="related-links"><a href="/r1">See also one</a><a href="/r2">See also two</a></div>
</article>
<footer><p>Copyright 2024 Example Corp. All rights reserved.</p></footer>
</body></html>
"""


class TestExtractMainContent:
    def test_retains_article_paragraphs(self) -> None:
        root = parse_html(_ARTICLE_HTML)
        config = ExtractionConfig()

        result = extract_main_content(root, config)

        assert "first paragraph of a real article" in result.text
        assert "second paragraph goes deeper" in result.text

    def test_excludes_navigation_menu(self) -> None:
        root = parse_html(_ARTICLE_HTML)
        result = extract_main_content(root, ExtractionConfig())

        assert "Home" not in result.text
        assert "Contact" not in result.text

    def test_excludes_sidebar_link_list(self) -> None:
        root = parse_html(_ARTICLE_HTML)
        result = extract_main_content(root, ExtractionConfig())

        assert "Related article one" not in result.text

    def test_excludes_footer(self) -> None:
        root = parse_html(_ARTICLE_HTML)
        result = extract_main_content(root, ExtractionConfig())

        assert "Copyright 2024" not in result.text

    def test_excludes_embedded_related_links_block_inside_article(self) -> None:
        root = parse_html(_ARTICLE_HTML)
        result = extract_main_content(root, ExtractionConfig())

        assert "See also one" not in result.text

    def test_falls_back_to_whole_document_when_no_candidate_scores_enough(self) -> None:
        html = "<html><body><p>Too short.</p></body></html>"
        root = parse_html(html)
        config = ExtractionConfig(min_main_content_chars=5)

        result = extract_main_content(root, config)

        assert "Too short." in result.text

    def test_empty_body_produces_empty_result(self) -> None:
        root = parse_html("<html><body></body></html>")

        result = extract_main_content(root, ExtractionConfig())

        assert result.text == ""
        assert result.retained_block_count == 0

    def test_positive_class_hint_boosts_container_over_unlabeled_sibling(self) -> None:
        html = """
        <html><body>
        <div>
        <p>Some short unlabeled paragraph without much text at all here.</p>
        </div>
        <div class="article-content">
        <p>A properly long paragraph living inside a container whose class name is a
        strong positive signal that this is the real article body, not boilerplate.</p>
        <p>A second paragraph reinforcing that this specific container is the winning
        candidate under the density and class/id hint heuristic used by this module.</p>
        </div>
        </body></html>
        """
        root = parse_html(html)
        result = extract_main_content(root, ExtractionConfig(min_main_content_chars=50))

        assert "strong positive signal" in result.text
        assert "unlabeled paragraph" not in result.text


class TestInlineElements:
    _DOCS_HTML = """
<html><body><nav><a href="/">Home</a></nav>
<div class="body" role="main">
<p>Tasks can be added to the group using
<a href="#create"><code><span>create_task()</span></code></a>.
All tasks are awaited when the context manager exits, and the group keeps running until
every task finishes, which makes structured concurrency the default for new code.</p>
<p>A second paragraph explains cancellation: when one task fails, the others are cancelled and
the exception is propagated to the code that entered the group, as an exception group.</p>
<div class="see-also"><a href="/a">Runners</a> <a href="/b">Streams</a></div>
</div></body></html>
"""

    def test_inline_links_stay_in_their_sentence(self) -> None:
        result = extract_main_content(parse_html(self._DOCS_HTML), ExtractionConfig())

        flat = " ".join(result.text.split())
        assert "added to the group using create_task(). All tasks are awaited" in flat

    def test_link_only_blocks_are_still_boilerplate(self) -> None:
        result = extract_main_content(parse_html(self._DOCS_HTML), ExtractionConfig())

        assert "Runners" not in result.text
        assert "Home" not in result.text
