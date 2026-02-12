from __future__ import annotations


PathElem = str | int


def parse_key_path(key_path: str) -> list[PathElem]:
    """
    Parse a "PlistBuddy-like" key path into a list of keys/indices.

    Syntax:
      - "A:B:C" refers to dict keys A -> B -> C
      - "CFBundleURLTypes:0:CFBundleURLSchemes:0" supports array indices (ints)
      - A leading ":" is allowed for convenience (PlistBuddy style)
    """
    s = key_path.strip()
    if s.startswith(":"):
        s = s[1:]
    if not s:
        raise ValueError("empty key path")
    parts = s.split(":")
    out: list[PathElem] = []
    for p in parts:
        if p == "":
            raise ValueError(f"invalid key path: {key_path}")
        if p.isdigit():
            out.append(int(p))
        else:
            out.append(p)
    return out
