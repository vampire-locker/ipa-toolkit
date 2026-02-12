from __future__ import annotations

"""
Apply high-level plist operation specs (`Op`) onto plist dictionaries.
"""

from typing import Sequence

from .plist_edit import array_add_string, array_remove_string, delete_value, set_value
from .types import Op


def _bool_from_str(s: str) -> bool:
    v = s.strip().lower()
    if v in ("true", "1", "yes", "y"):
        return True
    if v in ("false", "0", "no", "n"):
        return False
    raise ValueError(f"invalid bool: {s}")


def apply_ops(plist_obj: dict, ops: Sequence[Op]) -> None:
    for op in ops:
        try:
            if op.kind == "set_string":
                set_value(plist_obj, op.key_path, op.value or "")
            elif op.kind == "set_int":
                raw = op.value or "0"
                set_value(plist_obj, op.key_path, int(raw))
            elif op.kind == "set_bool":
                set_value(plist_obj, op.key_path, _bool_from_str(op.value or "false"))
            elif op.kind == "delete":
                delete_value(plist_obj, op.key_path)
            elif op.kind == "array_add":
                array_add_string(plist_obj, op.key_path, op.value or "")
            elif op.kind == "array_remove":
                array_remove_string(plist_obj, op.key_path, op.value or "")
            else:
                raise RuntimeError(f"Unknown op: {op.kind}")
        except (TypeError, ValueError) as e:
            suffix = f"={op.value}" if op.value is not None else ""
            raise SystemExit(
                f"Error: invalid plist operation {op.kind} on {op.key_path}{suffix}: {e}"
            ) from e
