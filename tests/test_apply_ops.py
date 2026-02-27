from ipa_toolkit.plist_ops import (
    apply_ops,
    rewrite_bundle_id_in_url_types,
    rewrite_bundle_id_strings,
)
from ipa_toolkit.types import Op


def test_apply_ops_reports_invalid_int_value() -> None:
    obj: dict = {}
    try:
        apply_ops(
            obj,
            [Op(scope="all", kind="set_int", key_path="A:B", value="12x")],
        )
        raise AssertionError("expected SystemExit")
    except SystemExit as e:
        msg = str(e)
        assert "invalid plist operation" in msg
        assert "set_int" in msg
        assert "A:B=12x" in msg


def test_apply_ops_reports_type_conflict_path() -> None:
    obj: dict = {"A": "string"}
    try:
        apply_ops(
            obj,
            [Op(scope="all", kind="set_string", key_path="A:B", value="v")],
        )
        raise AssertionError("expected SystemExit")
    except SystemExit as e:
        msg = str(e)
        assert "invalid plist operation" in msg
        assert "set_string" in msg
        assert "A:B=v" in msg


def test_rewrite_bundle_id_strings_rewrites_nested_values_without_double_replace() -> None:
    obj = {
        "Exact": "com.old.app",
        "Sub": "com.old.app.share",
        "AlreadyNew": "com.new.app.share",
        "Unchanged": "prefix.com.old.app",
        "Nested": {
            "Arr": [
                "com.old.app.widget",
                "com.new.app.widget",
                {"Deep": "com.old.app"},
            ]
        },
    }

    changed = rewrite_bundle_id_strings(
        obj,
        old_id="com.old.app",
        new_id="com.new.app",
    )

    assert changed == 4
    assert obj["Exact"] == "com.new.app"
    assert obj["Sub"] == "com.new.app.share"
    assert obj["AlreadyNew"] == "com.new.app.share"
    assert obj["Unchanged"] == "prefix.com.old.app"
    assert obj["Nested"]["Arr"][0] == "com.new.app.widget"
    assert obj["Nested"]["Arr"][1] == "com.new.app.widget"
    assert obj["Nested"]["Arr"][2]["Deep"] == "com.new.app"


def test_rewrite_bundle_id_in_url_types_rewrites_name_and_schemes() -> None:
    obj = {
        "CFBundleURLTypes": [
            {
                "CFBundleURLName": "com.old.app",
                "CFBundleURLSchemes": ["com.old.app", "com.old.app.share", "myapp"],
            },
            {
                "CFBundleURLName": "com.new.app",
                "CFBundleURLSchemes": ["com.new.app", "myapp2"],
            },
        ]
    }

    changed = rewrite_bundle_id_in_url_types(
        obj,
        old_id="com.old.app",
        new_id="com.new.app",
    )

    assert changed == 3
    first = obj["CFBundleURLTypes"][0]
    assert first["CFBundleURLName"] == "com.new.app"
    assert first["CFBundleURLSchemes"] == ["com.new.app", "com.new.app.share", "myapp"]
