import json
from pathlib import Path

import pytest

from html_content_extractor.models import DiscardReason, ExtractionConfig, NearDuplicateMode
from html_content_extractor.pipeline import ExtractionPipeline
from html_content_extractor.simhash import (
    NearDuplicateIndex,
    format_fingerprint,
    hamming_distance,
    parse_fingerprint,
    simhash64,
)

_BASE = (
    "Inverted indexes map every term to the documents that contain it. Search engines "
    "compress those postings lists with delta encoding and variable byte codes, and then "
    "rank candidate documents with BM25, which balances term frequency against document "
    "length. Link analysis such as PageRank adds a query independent authority signal. "
)
_ARTICLE = _BASE * 3
_ARTICLE_EDITED = _ARTICLE + " Updated on Monday."
_OTHER = (
    "The recipe needs flour, butter, two eggs and a pinch of salt. Knead the dough for ten "
    "minutes, let it rest in the fridge, then roll it out thinly and bake until golden. "
) * 3


def test_simhash_is_deterministic_and_case_insensitive() -> None:
    assert simhash64(_ARTICLE) == simhash64(_ARTICLE)
    assert simhash64("Search Engines RANK pages") == simhash64("search engines rank pages")
    assert simhash64("") == 0


def test_near_duplicates_are_close_and_different_texts_are_far() -> None:
    assert hamming_distance(simhash64(_ARTICLE), simhash64(_ARTICLE_EDITED)) <= 3
    assert hamming_distance(simhash64(_ARTICLE), simhash64(_OTHER)) > 10


def test_word_order_matters_through_shingles() -> None:
    assert simhash64("a b c d e f g h") != simhash64("h g f e d c b a")


def test_fingerprint_hex_round_trip() -> None:
    fingerprint = simhash64(_ARTICLE)
    text = format_fingerprint(fingerprint)
    assert len(text) == 16 and parse_fingerprint(text) == fingerprint
    with pytest.raises(ValueError):
        parse_fingerprint("abc")


def test_index_finds_every_fingerprint_within_distance() -> None:
    index = NearDuplicateIndex(max_distance=3)
    base = 0x0123_4567_89AB_CDEF
    index.add("same", base)
    index.add("three-bits", base ^ 0b10101)
    index.add("four-bits", base ^ 0b1111 << 40)
    index.add("far", ~base & (1 << 64) - 1)
    matches = index.find(base)
    assert [(m.url, m.distance) for m in matches] == [("same", 0), ("three-bits", 3)]
    assert len(index) == 4


def test_index_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError):
        NearDuplicateIndex(max_distance=32)


def _page(url: str, text: str) -> dict[str, object]:
    html = (
        f"<html><head><title>{url}</title></head>"
        f"<body><article><p>{text}</p></article></body></html>"
    )
    return {
        "url": url,
        "final_url": url,
        "status_code": 200,
        "headers": {"Content-Type": "text/html; charset=utf-8"},
        "html": html,
        "fetched_at": "2026-11-01T09:00:00+00:00",
        "depth": 0,
        "content_type": "text/html",
    }


def _run(
    tmp_path: Path, mode: NearDuplicateMode, pages: list[dict[str, object]]
) -> list[dict[str, object]]:
    pages_path = tmp_path / "pages.jsonl"
    pages_path.write_text("".join(json.dumps(p) + "\n" for p in pages), encoding="utf-8")
    config = ExtractionConfig(near_duplicate_mode=mode)
    with ExtractionPipeline(
        config, tmp_path / "documents.jsonl", tmp_path / "discarded.jsonl"
    ) as p:
        p.run(pages_path)
    return [
        json.loads(line) for line in (tmp_path / "documents.jsonl").read_text("utf-8").splitlines()
    ]


def test_pipeline_annotates_near_duplicates(tmp_path: Path) -> None:
    documents = _run(
        tmp_path,
        NearDuplicateMode.ANNOTATE,
        [
            _page("http://a", _ARTICLE),
            _page("http://b", _ARTICLE_EDITED),
            _page("http://c", _OTHER),
        ],
    )
    assert [d["near_duplicate_of"] for d in documents] == [None, "http://a", None]
    assert all(isinstance(d["simhash"], str) and len(d["simhash"]) == 16 for d in documents)


def test_pipeline_discards_near_duplicates(tmp_path: Path) -> None:
    documents = _run(
        tmp_path,
        NearDuplicateMode.DISCARD,
        [_page("http://a", _ARTICLE), _page("http://b", _ARTICLE_EDITED)],
    )
    assert [d["url"] for d in documents] == ["http://a"]
    discarded = json.loads((tmp_path / "discarded.jsonl").read_text("utf-8"))
    assert discarded["reason"] == DiscardReason.NEAR_DUPLICATE.value


def test_new_version_of_same_url_is_not_its_own_duplicate(tmp_path: Path) -> None:
    documents = _run(
        tmp_path,
        NearDuplicateMode.DISCARD,
        [_page("http://a", _ARTICLE), _page("http://a", _ARTICLE_EDITED)],
    )
    assert len(documents) == 2


def test_off_mode_writes_no_fingerprint(tmp_path: Path) -> None:
    (document,) = _run(tmp_path, NearDuplicateMode.OFF, [_page("http://a", _ARTICLE)])
    assert document["simhash"] is None


def test_priming_detects_duplicates_against_existing_corpus(tmp_path: Path) -> None:
    first = tmp_path / "first"
    first.mkdir()
    _run(first, NearDuplicateMode.ANNOTATE, [_page("http://a", _ARTICLE)])
    second = tmp_path / "second"
    second.mkdir()
    pages_path = second / "pages.jsonl"
    pages_path.write_text(json.dumps(_page("http://b", _ARTICLE_EDITED)) + "\n", encoding="utf-8")
    config = ExtractionConfig(near_duplicate_mode=NearDuplicateMode.DISCARD)
    with ExtractionPipeline(config, second / "documents.jsonl", second / "discarded.jsonl") as p:
        assert p.prime_near_duplicates(first / "documents.jsonl") == 1
        stats = p.run(pages_path)
    assert stats.discard_counts == {DiscardReason.NEAR_DUPLICATE: 1}
