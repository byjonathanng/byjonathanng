"""Connector interface every system must implement."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..model import Task


class Connector(ABC):
    """Uniform CRUD surface over one external system.

    Implementations must be idempotent where possible and should fill in
    ``Task.external_id`` and ``Task.updated_at`` when listing so the engine
    can match and order changes.
    """

    def __init__(self, name: str, settings: dict):
        self.name = name
        self.settings = settings

    @abstractmethod
    def list_tasks(self) -> list[Task]:
        """Return all tasks currently in this system (incl. completed)."""

    @abstractmethod
    def create_task(self, task: Task) -> str:
        """Create ``task`` and return its new external id."""

    @abstractmethod
    def update_task(self, external_id: str, task: Task) -> None:
        """Update the task identified by ``external_id`` to match ``task``."""

    @abstractmethod
    def delete_task(self, external_id: str) -> None:
        """Delete (or archive/complete) the task identified by id."""

    def healthcheck(self) -> None:
        """Raise if the connector cannot reach its backend. Override me."""
        self.list_tasks()
