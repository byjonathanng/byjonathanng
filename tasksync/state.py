"""SQLite state store: the memory that makes incremental sync possible.

For every logical task the store keeps one *link* per system, recording the
external id, the content hash at last sync, and the remote modified time at
last sync. Links sharing a ``cluster_id`` are "the same task" across
systems. Without this, the engine could not tell a brand-new task from an
edit, nor avoid re-creating copies on every run (echo loops).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from .model import as_utc

_SCHEMA = """
CREATE TABLE IF NOT EXISTS links (
    system      TEXT NOT NULL,
    external_id TEXT NOT NULL,
    cluster_id  TEXT NOT NULL,
    hash        TEXT NOT NULL,
    updated_at  TEXT,
    deleted     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (system, external_id)
);
CREATE INDEX IF NOT EXISTS idx_links_cluster ON links (cluster_id);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


@dataclass
class Link:
    system: str
    external_id: str
    cluster_id: str
    hash: str
    updated_at: Optional[datetime]
    deleted: bool = False


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return as_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


class StateStore:
    def __init__(self, path: str):
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- links ---------------------------------------------------------------

    def all_links(self) -> list[Link]:
        rows = self._conn.execute(
            "SELECT system, external_id, cluster_id, hash, updated_at, deleted FROM links"
        ).fetchall()
        return [self._row_to_link(r) for r in rows]

    def active_links(self) -> list[Link]:
        return [l for l in self.all_links() if not l.deleted]

    def upsert_link(self, link: Link) -> None:
        self._conn.execute(
            """
            INSERT INTO links (system, external_id, cluster_id, hash, updated_at, deleted)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(system, external_id) DO UPDATE SET
                cluster_id = excluded.cluster_id,
                hash       = excluded.hash,
                updated_at = excluded.updated_at,
                deleted    = excluded.deleted
            """,
            (
                link.system,
                link.external_id,
                link.cluster_id,
                link.hash,
                link.updated_at.isoformat() if link.updated_at else None,
                1 if link.deleted else 0,
            ),
        )

    def mark_deleted(self, system: str, external_id: str) -> None:
        self._conn.execute(
            "UPDATE links SET deleted = 1 WHERE system = ? AND external_id = ?",
            (system, external_id),
        )

    def remove_link(self, system: str, external_id: str) -> None:
        self._conn.execute(
            "DELETE FROM links WHERE system = ? AND external_id = ?",
            (system, external_id),
        )

    def commit(self) -> None:
        self._conn.commit()

    # -- cluster ids ---------------------------------------------------------

    def next_cluster_id(self) -> str:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = 'cluster_seq'"
        ).fetchone()
        current = int(row["value"]) if row else 0
        nxt = current + 1
        self._conn.execute(
            "INSERT INTO meta (key, value) VALUES ('cluster_seq', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(nxt),),
        )
        return f"c{nxt:08d}"

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _row_to_link(row: sqlite3.Row) -> Link:
        return Link(
            system=row["system"],
            external_id=row["external_id"],
            cluster_id=row["cluster_id"],
            hash=row["hash"],
            updated_at=_parse_dt(row["updated_at"]),
            deleted=bool(row["deleted"]),
        )

    def links_by_key(self) -> dict[tuple[str, str], Link]:
        return {(l.system, l.external_id): l for l in self.all_links()}

    def cluster_members(self, links: Iterable[Link]) -> dict[str, dict[str, Link]]:
        """Group links by cluster_id -> {system: Link}."""
        out: dict[str, dict[str, Link]] = {}
        for link in links:
            out.setdefault(link.cluster_id, {})[link.system] = link
        return out
