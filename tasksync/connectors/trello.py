"""Trello connector (REST via ``py-trello``).

Tasks map to cards in one configured list. Completion is represented with
Trello's native "due complete" flag, so a card never has to move lists to
be marked done. Card name -> title, description -> notes, due -> due.
Trello has no native priority, so priority is carried in the canonical
model but not written to Trello.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ..model import PRIORITY_NONE, Task
from .base import Connector


class TrelloConnector(Connector):
    def __init__(self, name: str, settings: dict):
        super().__init__(name, settings)
        self._client = None
        self._list = None
        self.list_id = settings["list_id"]
        # Archive instead of hard-delete on delete by default.
        self.delete_mode = settings.get("delete_mode", "archive")  # archive | delete

    @property
    def client(self):
        if self._client is None:
            from trello import TrelloClient

            self._client = TrelloClient(
                api_key=self.settings["api_key"],
                token=self.settings["token"],
            )
        return self._client

    @property
    def list(self):
        if self._list is None:
            self._list = self.client.get_list(self.list_id)
        return self._list

    # -- mapping -------------------------------------------------------------

    @staticmethod
    def _to_task(card) -> Task:
        due: Optional[datetime] = getattr(card, "due_date", None) or None
        # py-trello exposes due completion as `is_due_complete`.
        done = bool(getattr(card, "is_due_complete", False))
        updated = getattr(card, "dateLastActivity", None)
        return Task(
            title=card.name or "",
            notes=card.description or "",
            done=done,
            due=due,
            priority=PRIORITY_NONE,
            external_id=card.id,
            updated_at=updated,
            raw={"url": getattr(card, "url", None)},
        )

    # -- CRUD ----------------------------------------------------------------

    def list_tasks(self) -> list[Task]:
        cards = self.list.list_cards(card_filter="open")
        tasks = []
        for card in cards:
            card.fetch()  # populate description / due / due-complete
            tasks.append(self._to_task(card))
        return tasks

    def create_task(self, task: Task) -> str:
        card = self.list.add_card(name=task.title or "(untitled)", desc=task.notes)
        if task.due is not None:
            card.set_due(task.due)
            if task.done:
                card.set_due_complete()
        return card.id

    def update_task(self, external_id: str, task: Task) -> None:
        card = self.client.get_card(external_id)
        card.fetch()
        if card.name != task.title:
            card.set_name(task.title or "(untitled)")
        if (card.description or "") != task.notes:
            card.set_description(task.notes)
        if task.due is not None:
            card.set_due(task.due)
        elif getattr(card, "due_date", None):
            card.remove_due()
        currently_done = bool(getattr(card, "is_due_complete", False))
        if task.done and not currently_done:
            # `due complete` requires a due date; default to now if missing.
            if not getattr(card, "due_date", None):
                card.set_due(datetime.now(timezone.utc))
            card.set_due_complete()
        elif not task.done and currently_done:
            card.set_due_incomplete()

    def delete_task(self, external_id: str) -> None:
        card = self.client.get_card(external_id)
        if self.delete_mode == "delete":
            card.delete()
        else:
            card.set_closed(True)
