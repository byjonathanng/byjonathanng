"""An in-memory connector used by the tests (no network required)."""

from __future__ import annotations

import copy
import itertools

from tasksync.connectors.base import Connector
from tasksync.model import Task, utcnow


class MemoryConnector(Connector):
    def __init__(self, name: str, settings: dict | None = None):
        super().__init__(name, settings or {})
        self.tasks: dict[str, Task] = {}
        self._ids = itertools.count(1)

    def _new_id(self) -> str:
        return f"{self.name}-{next(self._ids)}"

    def list_tasks(self) -> list[Task]:
        out = []
        for ext_id, task in self.tasks.items():
            clone = copy.deepcopy(task)
            clone.external_id = ext_id
            out.append(clone)
        return out

    def create_task(self, task: Task) -> str:
        ext_id = self._new_id()
        stored = copy.deepcopy(task)
        stored.external_id = ext_id
        stored.updated_at = utcnow()
        self.tasks[ext_id] = stored
        return ext_id

    def update_task(self, external_id: str, task: Task) -> None:
        stored = copy.deepcopy(task)
        stored.external_id = external_id
        stored.updated_at = utcnow()
        self.tasks[external_id] = stored

    def delete_task(self, external_id: str) -> None:
        self.tasks.pop(external_id, None)

    # Test helpers ----------------------------------------------------------

    def seed(self, task: Task) -> str:
        return self.create_task(task)
