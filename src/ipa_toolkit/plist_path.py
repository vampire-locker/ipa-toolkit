from __future__ import annotations

PathElem = str | int


def parse_key_path(key_path: str) -> list[PathElem]:
    """
    将 PlistBuddy 风格路径解析为字典键/数组索引序列。

    语法说明：
    - `A:B:C` 表示字典键 `A -> B -> C`。
    - `CFBundleURLTypes:0:CFBundleURLSchemes:0` 支持数组索引。
    - 允许以前导 `:` 开头，兼容 PlistBuddy 习惯。
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
