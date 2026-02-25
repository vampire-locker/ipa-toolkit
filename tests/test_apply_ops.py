from ipa_toolkit.plist_ops import apply_ops
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
