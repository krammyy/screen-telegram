"""Hard machine lock baked into source.

Unlike config.json, this cannot be casually rewritten with --bind on another PC
unless ALLOW_REBIND is explicitly set True (owner-only).
"""

from __future__ import annotations

# Fingerprint of the only allowed Windows machine (sha256[:32]).
# Filled by: python main.py --bind --lock
OWNER_MACHINE_ID = ""

# Keep False so copies of the app cannot re-bind themselves on another PC.
ALLOW_REBIND = True
