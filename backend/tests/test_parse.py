from app.scrapers.base import Source, parse

SRC = Source(name="T", search_url="x/{q}", base_url="https://t.example")

HTML = """<script type="application/ld+json">
{"@graph":[
 {"@type":"Product","name":"Oyster Mushrooms 150g","url":"/p/1","offers":{"price":"2.25"}},
 {"@type":"Product","name":"King Oyster Mushrooms 150g","url":"/p/2"},
 {"@type":"Product","name":"Chestnut Mushrooms","url":"/p/3"}]}
</script>"""


def test_filters_king_and_non_matches():
    out = parse(HTML, SRC, "oyster mushrooms")
    assert [p.name for p in out] == ["Oyster Mushrooms 150g"]
    assert out[0].price == "£2.25"
    assert out[0].url == "https://t.example/p/1"


def test_king_allowed_when_asked():
    out = parse(HTML, SRC, "king oyster")
    assert len(out) == 1
