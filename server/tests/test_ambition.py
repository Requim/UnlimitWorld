"""本局执念目录测试。"""

from server.domain.ambition import draw_ambition_offers, find_ambition, get_catalog


def test_catalog_has_unique_ids():
    catalog = get_catalog()
    assert len(catalog) >= 6
    assert len({item.id for item in catalog}) == len(catalog)


def test_draw_ambition_offers_returns_offer_dicts():
    offers = draw_ambition_offers(3)
    assert len(offers) == 3
    assert len({item.id for item in offers}) == 3
    payload = offers[0].to_offer()
    assert {"id", "title", "summary", "target", "progress_label", "reward_hint"} <= set(payload)


def test_find_ambition():
    ambition = find_ambition("taunt_heaven")
    assert ambition is not None
    assert ambition.title == "嘴硬十回合"
    assert find_ambition("not_exists") is None
