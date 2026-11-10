"""Manage the exclusion list (the manual mirror of Instagram mute state).

Usage:
    python -m app.exclusions list
    python -m app.exclusions add <sender-id-or-username>
    python -m app.exclusions remove <sender-id-or-username>

The store matches whatever identifier the webhook carries for the sender,
so add the same form the app is configured to compare — in practice the
sender id, or the username if you extend the resolver to match on it.
"""

from __future__ import annotations

import sys

from .config import Settings
from .store import Store


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    store = Store(Settings.from_env().database_path)
    command = argv[1]
    if command == "list":
        for sender in store.list_exclusions():
            print(sender)
    elif command == "add" and len(argv) == 3:
        store.add_exclusion(argv[2])
        print(f"excluded: {argv[2]}")
    elif command == "remove" and len(argv) == 3:
        store.remove_exclusion(argv[2])
        print(f"removed: {argv[2]}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
