"""
CLI 与 IPA 处理流程共享的轻量类型定义。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Op:
    """描述一次对 `Info.plist` 的可序列化操作。"""

    # `scope` 作用域：
    # - `all`：主应用与扩展都生效。
    # - `main`：仅主应用生效。
    # - `ext`：仅扩展/服务生效。
    scope: str
    # `kind` 操作类型：
    # - `set_string` / `set_int` / `set_bool`
    # - `delete`
    # - `array_add` / `array_remove`
    kind: str
    key_path: str
    value: str | None = None
