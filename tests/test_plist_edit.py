from ipa_toolkit.plist_edit import array_add_string, array_remove_string, delete_value, set_value


def test_set_value_creates_containers() -> None:
    obj: dict = {}
    set_value(obj, "A:B:0:C", "v")
    assert obj == {"A": {"B": [{"C": "v"}]}}


def test_delete_value_missing_is_noop() -> None:
    obj: dict = {"A": {"B": [1, 2, 3]}}
    delete_value(obj, "A:B:10")
    assert obj == {"A": {"B": [1, 2, 3]}}


def test_array_add_remove_string() -> None:
    obj: dict = {}
    array_add_string(obj, "LSApplicationQueriesSchemes", "weixin")
    array_add_string(obj, "LSApplicationQueriesSchemes", "alipays")
    array_remove_string(obj, "LSApplicationQueriesSchemes", "weixin")
    assert obj["LSApplicationQueriesSchemes"] == ["alipays"]
