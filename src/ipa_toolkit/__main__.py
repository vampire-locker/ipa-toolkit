"""
`python -m ipa_toolkit` 命令入口。

该入口仅用于便捷调用，实际会转发到 `ipa_toolkit.cli:main`。
"""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
