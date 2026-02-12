"""
Shared small types used by the CLI and the IPA processing pipeline.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Op:
    # scope:
    #   - "all": apply to main app + extensions
    #   - "main": apply only to the main .app
    #   - "ext": apply only to extensions/services under the main app
    scope: str
    # kind:
    #   - set_string / set_int / set_bool
    #   - delete
    #   - array_add / array_remove
    kind: str
    key_path: str
    value: str | None = None
