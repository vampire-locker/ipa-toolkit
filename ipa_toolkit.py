#!/usr/bin/env python3
"""
Source-checkout entrypoint.

Allows running the tool without installing it:
  python3 ipa_toolkit.py ...
"""

import os
import sys

# Support running from a source checkout without installation by adding `src/`
# to sys.path.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# Make this module behave like a package shim when imported as `ipa_toolkit`.
# This avoids shadowing `src/ipa_toolkit/` during test/import usage.
__path__ = [os.path.join(_SRC, "ipa_toolkit")]


def main(argv: list[str] | None = None) -> int:
    from ipa_toolkit.cli import main as _main

    return _main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
