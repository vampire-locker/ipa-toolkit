"""
`Info.plist` 读写与路径化修改工具。

设计原则：
- 仅在设置值时按需创建中间容器（`dict` 或 `list`）。
- 删除操作采用尽力而为策略（路径不存在时忽略）。
"""

from __future__ import annotations

import plistlib
from typing import Any

from .plist_path import PathElem, parse_key_path


def load_plist(path: str) -> Any:
    """从磁盘读取 plist（自动识别 XML/Binary）并返回对象。"""
    with open(path, "rb") as f:
        return plistlib.load(f)


def save_plist_binary(path: str, obj: Any) -> None:
    """将对象以二进制 plist 格式写回磁盘。"""
    data = plistlib.dumps(obj, fmt=plistlib.FMT_BINARY, sort_keys=False)
    with open(path, "wb") as f:
        f.write(data)


def _ensure_list_len(lst: list, idx: int) -> None:
    """确保列表长度至少到 `idx`，不足位置补 `None`。"""
    while len(lst) <= idx:
        lst.append(None)


def _walk_create(root: Any, path: list[PathElem]) -> tuple[Any, PathElem]:
    """按路径遍历到叶子前一层，并在必要时创建中间容器，返回 `(parent, leaf_key)`。"""
    cur = root
    for i, elem in enumerate(path[:-1]):
        nxt = path[i + 1]
        if isinstance(elem, int):
            if not isinstance(cur, list):
                raise TypeError("array index used on non-list container")
            _ensure_list_len(cur, elem)
            if cur[elem] is None:
                cur[elem] = [] if isinstance(nxt, int) else {}
            cur = cur[elem]
        else:
            if not isinstance(cur, dict):
                raise TypeError("dict key used on non-dict container")
            if elem not in cur or cur[elem] is None:
                cur[elem] = [] if isinstance(nxt, int) else {}
            cur = cur[elem]
    return cur, path[-1]


def set_value(root: Any, key_path: str, value: Any) -> None:
    """在指定 key path 处设置值（必要时自动创建中间结构）。"""
    path = parse_key_path(key_path)
    parent, leaf = _walk_create(root, path)
    if isinstance(leaf, int):
        if not isinstance(parent, list):
            raise TypeError("array index used on non-list container")
        _ensure_list_len(parent, leaf)
        parent[leaf] = value
    else:
        if not isinstance(parent, dict):
            raise TypeError("dict key used on non-dict container")
        parent[leaf] = value


def delete_value(root: Any, key_path: str) -> None:
    """删除指定 key path 对应值；路径不存在时静默跳过。"""
    path = parse_key_path(key_path)
    cur = root
    for elem in path[:-1]:
        if isinstance(elem, int):
            if not isinstance(cur, list) or elem >= len(cur):
                return
            cur = cur[elem]
        else:
            if not isinstance(cur, dict) or elem not in cur:
                return
            cur = cur[elem]

    leaf = path[-1]
    if isinstance(leaf, int):
        if isinstance(cur, list) and 0 <= leaf < len(cur):
            cur.pop(leaf)
    else:
        if isinstance(cur, dict) and leaf in cur:
            del cur[leaf]


def _get_or_create_array(root: Any, key_path: str) -> list:
    """获取或创建目标数组节点，不是数组时抛出类型错误。"""
    path = parse_key_path(key_path)
    parent, leaf = _walk_create(root, path)
    if isinstance(leaf, int):
        raise TypeError("array path must point to a key, not an index")
    if not isinstance(parent, dict):
        raise TypeError("dict key used on non-dict container")
    if leaf not in parent or parent[leaf] is None:
        parent[leaf] = []
    if not isinstance(parent[leaf], list):
        raise TypeError(f"target is not an array: {key_path}")
    return parent[leaf]


def array_add_string(root: Any, key_path: str, value: str) -> None:
    """向目标数组追加一个字符串元素。"""
    arr = _get_or_create_array(root, key_path)
    arr.append(value)


def array_remove_string(root: Any, key_path: str, value: str) -> None:
    """从目标数组中删除所有匹配字符串元素。"""
    arr = _get_or_create_array(root, key_path)
    arr[:] = [x for x in arr if x != value]
