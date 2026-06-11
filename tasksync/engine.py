"""The sync engine: hub-and-spoke with last-write-wins.

Each run:

1. Pull every task from every enabled system.
2. Reconcile against the state store to classify each task as *new*,
   *changed* (content hash differs), *unchanged*, or *deleted* (a known
   link whose task vanished).
3. Group tasks into clusters (one logical task across systems). New tasks
   with identical normalized titles are merged into one cluster to avoid
   cross-creating duplicates on first run.
4. For each cluster pick a winner — the most recently modified change (or a
   deletion) — and propagate it to the other systems.
5. Record new hashes/timestamps so the next run sees a clean baseline.

Conflict policy is last-write-wins by modification time. A deletion is
timestamped "now", so an intentional delete generally wins over a stale
edit elsewhere.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .connectors.base import Connector
from .model import Task, utcnow
from .state import Link, StateStore

log = logging.getLogger("tasksync.engine")

_MIN_DT = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip().lower())


@dataclass
class Change:
    """A pending write the engine decided to make (also used for dry-run)."""

    action: str  # create | update | delete
    system: str
    cluster_id: str
    title: str
    external_id: Optional[str] = None


@dataclass
class SyncReport:
    changes: list[Change] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.changes and not self.errors:
            return "Already in sync — nothing to do."
        counts: dict[str, int] = {}
        for c in self.changes:
            counts[c.action] = counts.get(c.action, 0) + 1
        parts = [f"{n} {action}" for action, n in sorted(counts.items())]
        line = ", ".join(parts) if parts else "no changes"
        if self.errors:
            line += f"; {len(self.errors)} error(s)"
        return line


class SyncEngine:
    def __init__(
        self,
        connectors: dict[str, Connector],
        state: StateStore,
        dry_run: bool = False,
        propagate_deletes: bool = True,
    ):
        self.connectors = connectors
        self.state = state
        self.dry_run = dry_run
        self.propagate_deletes = propagate_deletes

    # -- public --------------------------------------------------------------

    def sync(self) -> SyncReport:
        report = SyncReport()

        current = self._fetch_all(report)
        links = self.state.links_by_key()

        observed, links = self._classify(current, links)
        clusters = self._group_clusters(links)

        for cluster_id, members in clusters.items():
            try:
                self._reconcile_cluster(cluster_id, members, observed, links, report)
            except Exception as exc:  # one bad cluster shouldn't kill the run
                msg = f"cluster {cluster_id}: {exc}"
                log.exception(msg)
                report.errors.append(msg)

        if not self.dry_run:
            self.state.commit()
        return report

    # -- pipeline stages -----------------------------------------------------

    def _fetch_all(self, report: SyncReport) -> dict[str, dict[str, Task]]:
        current: dict[str, dict[str, Task]] = {}
        for name, connector in self.connectors.items():
            try:
                tasks = connector.list_tasks()
            except Exception as exc:
                msg = f"{name}: list_tasks failed: {exc}"
                log.exception(msg)
                report.errors.append(msg)
                current[name] = {}
                continue
            current[name] = {t.external_id: t for t in tasks if t.external_id}
        return current

    def _classify(
        self,
        current: dict[str, dict[str, Task]],
        links: dict[tuple[str, str], Link],
    ):
        """Attach the live Task to each observed system/cluster and assign
        clusters to brand-new tasks (merging by title where possible)."""
        # cluster_id -> system -> (task | None for deletion)
        observed: dict[str, dict[str, Optional[Task]]] = {}
        # Track new-this-run titles so duplicates across systems merge.
        new_by_title: dict[str, str] = {}

        # Seed title index with existing single-member clusters? Keep it to
        # this run's new tasks only to stay predictable.
        for system, tasks in current.items():
            for ext_id, task in tasks.items():
                key = (system, ext_id)
                link = links.get(key)
                if link is not None:
                    observed.setdefault(link.cluster_id, {})[system] = task
                    continue
                # New task in this system.
                title_key = _norm_title(task.title)
                cluster_id = new_by_title.get(title_key) if title_key else None
                if cluster_id is None:
                    cluster_id = self.state.next_cluster_id()
                    if title_key:
                        new_by_title[title_key] = cluster_id
                new_link = Link(
                    system=system,
                    external_id=ext_id,
                    cluster_id=cluster_id,
                    hash="",  # empty sentinel: never synced yet -> counts as a change
                    updated_at=task.updated_at,
                    deleted=False,
                )
                links[key] = new_link
                observed.setdefault(cluster_id, {})[system] = task

        # Deletions: known, active links whose task is gone.
        for (system, ext_id), link in list(links.items()):
            if link.deleted:
                continue
            if ext_id not in current.get(system, {}):
                observed.setdefault(link.cluster_id, {}).setdefault(system, None)

        return observed, links

    def _group_clusters(
        self, links: dict[tuple[str, str], Link]
    ) -> dict[str, dict[str, Link]]:
        clusters: dict[str, dict[str, Link]] = {}
        for link in links.values():
            clusters.setdefault(link.cluster_id, {})[link.system] = link
        return clusters

    def _reconcile_cluster(
        self,
        cluster_id: str,
        members: dict[str, Link],
        observed: dict[str, dict[str, Optional[Task]]],
        links: dict[tuple[str, str], Link],
        report: SyncReport,
    ) -> None:
        seen = observed.get(cluster_id, {})

        # Build candidate events: (timestamp, kind, system, task|None)
        events: list[tuple[datetime, str, str, Optional[Task]]] = []
        for system, task in seen.items():
            link = members.get(system)
            if task is None:
                # Deletion event — timestamp "now" so a real delete tends to win.
                if link is not None and not link.deleted:
                    events.append((utcnow(), "delete", system, None))
                continue
            stored_hash = link.hash if link else None
            if stored_hash != task.content_hash():
                ts = task.updated_at or utcnow()
                events.append((ts, "update", system, task))

        if not events:
            return  # nothing changed in this cluster

        events.sort(key=lambda e: e[0] or _MIN_DT)
        _, kind, win_system, win_task = events[-1]

        if kind == "delete":
            if self.propagate_deletes:
                self._apply_delete(cluster_id, members, win_system, report)
            return

        self._apply_update(cluster_id, members, seen, win_system, win_task, links, report)

    # -- effects -------------------------------------------------------------

    def _apply_delete(
        self,
        cluster_id: str,
        members: dict[str, Link],
        win_system: str,
        report: SyncReport,
    ) -> None:
        for system, link in members.items():
            connector = self.connectors.get(system)
            if connector is None or link.deleted:
                continue
            if system != win_system:
                report.changes.append(
                    Change("delete", system, cluster_id, "", link.external_id)
                )
                if not self.dry_run:
                    connector.delete_task(link.external_id)
            if not self.dry_run:
                self.state.mark_deleted(system, link.external_id)

    def _apply_update(
        self,
        cluster_id: str,
        members: dict[str, Link],
        seen: dict[str, Optional[Task]],
        win_system: str,
        win_task: Task,
        links: dict[tuple[str, str], Link],
        report: SyncReport,
    ) -> None:
        winning_hash = win_task.content_hash()

        for system, connector in self.connectors.items():
            link = members.get(system)

            if system == win_system:
                # Just refresh our baseline for the source of truth.
                if not self.dry_run and link is not None:
                    link.hash = winning_hash
                    link.updated_at = win_task.updated_at
                    self.state.upsert_link(link)
                continue

            payload = win_task  # same canonical content for everyone

            if link is None or link.deleted:
                # Missing in this system -> create it.
                report.changes.append(
                    Change("create", system, cluster_id, payload.title)
                )
                if not self.dry_run:
                    new_id = connector.create_task(payload)
                    new_link = Link(
                        system=system,
                        external_id=new_id,
                        cluster_id=cluster_id,
                        hash=winning_hash,
                        updated_at=utcnow(),
                        deleted=False,
                    )
                    links[(system, new_id)] = new_link
                    self.state.upsert_link(new_link)
                continue

            # Present already — only write if its content actually differs.
            existing = seen.get(system)
            existing_hash = (
                existing.content_hash() if existing is not None else link.hash
            )
            if existing_hash == winning_hash:
                if not self.dry_run:
                    link.hash = winning_hash
                    self.state.upsert_link(link)
                continue

            report.changes.append(
                Change("update", system, cluster_id, payload.title, link.external_id)
            )
            if not self.dry_run:
                connector.update_task(link.external_id, payload)
                link.hash = winning_hash
                link.updated_at = utcnow()
                self.state.upsert_link(link)
