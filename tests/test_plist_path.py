from ipa_toolkit.plist_path import parse_key_path


def test_parse_key_path_simple() -> None:
    assert parse_key_path("A:B:C") == ["A", "B", "C"]


def test_parse_key_path_with_indices() -> None:
    assert parse_key_path("CFBundleURLTypes:0:CFBundleURLSchemes:1") == [
        "CFBundleURLTypes",
        0,
        "CFBundleURLSchemes",
        1,
    ]


def test_parse_key_path_leading_colon() -> None:
    assert parse_key_path(":A:0") == ["A", 0]
