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

from ipa_toolkit.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
