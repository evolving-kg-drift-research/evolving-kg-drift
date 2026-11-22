from __future__ import annotations

import pandas as pd
import pytest

from kg_pipeline.tuoitre_parser_v2 import ParseError, matches_domain_keywords, parse_tuoitre
from scripts.x1_prepare_pilot import draw, order_key

PAGE = """<html><head><script type="application/ld+json">{{"datePublished": "{date}"}}</script></head><body>
<article><a>Tin liên quan ngắn</a></article>
<h1 class="detail-title">OpenAI ra mắt GPT-5</h1>
<p class="detail-sapo">Sapo của bài.</p>
<div class="detail-content" data-role="content">
  <figure class="VCSortableInPreviewMode" type="Photo"><p class="PhotoCMS_Caption">Chú thích ảnh</p></figure>
  <p>Đoạn một nói về &#x41;I.</p>
  <div class="kbwscwl-relatedbox type-1 tuoitre"><p>Tin khác</p></div>
  <h2>Tiêu đề phụ</h2><p>Đoạn hai.</p>
</div></body></html>"""


def test_parser_reads_article_fields_and_drops_boxes() -> None:
    parsed = parse_tuoitre(PAGE.format(date="2026-01-13T15:31:00+07:00"))
    assert parsed["text"] == "OpenAI ra mắt GPT-5\nSapo của bài.\nĐoạn một nói về AI.\nTiêu đề phụ\nĐoạn hai."
    assert parsed["published_at"] == "2026-01-13T15:31:00+07:00"


@pytest.mark.parametrize("html", [PAGE.format(date="2026-01-13T15:31:00"),  # no timezone
                                  PAGE.replace("datePublished", "dateModified").format(date="2026-01-13T15:31:00+07:00"),
                                  PAGE.replace('data-role="content"', "").format(date="2026-01-13T15:31:00+07:00")])
def test_parser_fails_closed(html: str) -> None:
    with pytest.raises(ParseError):
        parse_tuoitre(html)


def test_keyword_rule_case_and_word_boundaries() -> None:
    kw = ["AI", "trí tuệ nhân tạo", "LLM"]
    assert matches_domain_keywords("Công cụ AI mới", kw) == ["AI"]
    assert matches_domain_keywords("ai cũng biết; AIDA; Trí Tuệ Nhân Tạo", kw) == ["trí tuệ nhân tạo"]
    assert matches_domain_keywords("không liên quan", kw) == []


def test_draw_is_deterministic_disjoint_and_proportional() -> None:
    ids = [f"id{i}" for i in range(90)]
    frame = pd.DataFrame({"item_id": ids, "tertile": [i % 3 for i in range(90)],
                          "order_key": [order_key(i) for i in ids]})
    gold, dev = draw(frame, 10, 4)
    gold2, dev2 = draw(frame.sample(frac=1, random_state=0), 10, 4)
    assert list(gold.item_id) == list(gold2.item_id) and list(dev.item_id) == list(dev2.item_id)
    assert len(gold) == 10 and len(dev) == 4 and not set(gold.item_id) & set(dev.item_id)
    assert sorted(gold.tertile.value_counts().tolist()) == [3, 3, 4]
    for t, group in frame.sort_values("order_key").groupby("tertile"):  # gold = lowest keys, dev = next
        g = gold[gold.tertile == t].item_id.tolist()
        assert group.item_id.tolist()[: len(g)] == g
