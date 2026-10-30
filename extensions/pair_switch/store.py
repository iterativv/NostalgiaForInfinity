"""Separate SQLite journal with compare-and-swap, not a Freqtrade DB editor."""

import json
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path
from collections.abc import Iterator

from .models import Intent, Phase, Request, SwitchError, TERMINAL


class Store:
  def __init__(self, path: Path):
    if not path.is_absolute():
      raise SwitchError("The journal path must be absolute.")
    self.path = path

  @contextmanager
  def connection(self) -> Iterator[sqlite3.Connection]:
    # mode=rw prevents a missing journal from becoming an empty replacement.
    with closing(sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=5)) as db:
      with db:
        yield db

  def initialize(self, binding: str) -> None:
    self.path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(self.path, timeout=5)) as db:
      with db:
        db.execute("PRAGMA synchronous=FULL")
        db.execute("CREATE TABLE IF NOT EXISTS binding (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)")
        db.execute(
          "CREATE TABLE IF NOT EXISTS intents ("
          "token TEXT PRIMARY KEY, source_id INTEGER UNIQUE NOT NULL, "
          "phase TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL)"
        )
        db.execute(
          "CREATE UNIQUE INDEX IF NOT EXISTS one_active ON intents ((1)) "
          "WHERE phase NOT IN ('complete', 'cancelled', 'rejected')"
        )
        row = db.execute("SELECT value FROM binding WHERE id=1").fetchone()
        if row is not None and row[0] != binding:
          raise SwitchError("This journal belongs to a different bot database/configuration.")
        db.execute("INSERT OR IGNORE INTO binding VALUES (1, ?)", (binding,))
    self.path.chmod(0o600)

  def submit(self, request: Request) -> Intent:
    with self.connection() as db:
      db.execute("BEGIN IMMEDIATE")
      old = db.execute("SELECT payload FROM intents WHERE token=?", (request.token,)).fetchone()
      if old is not None:
        intent = Intent.model_validate_json(old[0])
        if intent.request != request:
          raise SwitchError("A token cannot be reused with different request data.")
        return intent
      intent = Intent(request=request)
      try:
        db.execute(
          "INSERT INTO intents VALUES (?, ?, ?, ?, ?)",
          (request.token, request.source_id, intent.phase.value, 0, intent.model_dump_json()),
        )
      except sqlite3.IntegrityError as exc:
        raise SwitchError("Another request is active or this source trade was already requested.") from exc
      return intent

  def active(self) -> Intent | None:
    with self.connection() as db:
      row = db.execute(
        "SELECT payload FROM intents WHERE phase NOT IN ('complete', 'cancelled', 'rejected')"
      ).fetchone()
    return Intent.model_validate_json(row[0]) if row else None

  def all(self) -> list[Intent]:
    with self.connection() as db:
      rows = db.execute("SELECT payload FROM intents ORDER BY rowid").fetchall()
    return [Intent.model_validate_json(row[0]) for row in rows]

  def save(self, old: Intent, new: Intent) -> Intent:
    updated = new.model_copy(update={"revision": old.revision + 1})
    # Reparse model_copy's changes; it deliberately does not validate updates.
    updated = Intent.model_validate_json(updated.model_dump_json())
    with self.connection() as db:
      count = db.execute(
        "UPDATE intents SET phase=?, revision=?, payload=? WHERE token=? AND revision=?",
        (updated.phase.value, updated.revision, updated.model_dump_json(), old.request.token, old.revision),
      ).rowcount
      if count != 1:
        raise SwitchError("The request changed concurrently; admission was refused.")
    return updated

  def cancel(self, token: str) -> Intent:
    intent = next((item for item in self.all() if item.request.token == token), None)
    if intent is None:
      raise SwitchError("Unknown request.")
    if intent.phase in TERMINAL:
      return intent
    if intent.phase not in (Phase.REQUESTED, Phase.CLOSING, Phase.READY):
      raise SwitchError("Entry may already exist. Reconcile on exchange; never rearm this request.")
    return self.save(
      intent,
      intent.model_copy(
        update={
          "phase": Phase.CANCELLED,
          "note": "Cancelled future entry; an existing exit order is not undone.",
        }
      ),
    )

  def binding(self) -> str:
    with self.connection() as db:
      row = db.execute("SELECT value FROM binding WHERE id=1").fetchone()
    if row is None:
      raise SwitchError("Start the extension strategy before submitting requests.")
    return str(row[0])

  def json_status(self) -> str:
    return json.dumps([item.model_dump(mode="json") for item in self.all()], indent=2)
