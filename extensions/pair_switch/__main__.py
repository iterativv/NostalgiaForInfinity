"""Local journal CLI. This program has no exchange or REST client."""

import argparse
import sqlite3
import sys
from pathlib import Path

from pydantic import ValidationError

from .models import Request, SwitchError
from .store import Store


def main() -> int:
  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--database", required=True, type=Path)
  commands = parser.add_subparsers(dest="command", required=True)
  commands.add_parser("status")
  submit = commands.add_parser("submit")
  submit.add_argument("request", type=Path, help="JSON request with stable token and UTC expiry.")
  cancel = commands.add_parser("cancel")
  cancel.add_argument("token")
  args = parser.parse_args()
  try:
    store = Store(args.database)
    store.binding()
    match args.command:
      case "submit":
        request = Request.model_validate_json(args.request.read_text())
        print(store.submit(request).model_dump_json(indent=2))
      case "cancel":
        print(store.cancel(args.token).model_dump_json(indent=2))
      case "status":
        print(store.json_status())
    return 0
  except (SwitchError, ValidationError, OSError, sqlite3.Error) as exc:
    print(str(exc), file=sys.stderr)
    return 2


if __name__ == "__main__":
  raise SystemExit(main())
