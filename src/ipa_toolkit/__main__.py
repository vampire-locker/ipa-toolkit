"""
`python -m ipa_toolkit` entrypoint.

This is mainly for convenience; the installed console script `ipa-toolkit` calls
the same `ipa_toolkit.cli:main`.
"""

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
