"""iOS Reminders connector via iCloud CalDAV.

iOS Reminders has no public cloud API, but iCloud exposes each Reminders
list as a CalDAV calendar of ``VTODO`` items. Authenticate with your Apple
ID email and an **app-specific password** (appleid.apple.com -> Sign-In and
Security -> App-Specific Passwords). Changes here appear on every device
signed into the same iCloud account.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from ..model import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    PRIORITY_NONE,
    Task,
)
from .base import Connector

ICLOUD_CALDAV_URL = "https://caldav.icloud.com/"

# Canonical priority <-> iCalendar PRIORITY (1=highest .. 9=lowest, 0=none).
_PRIORITY_TO_ICAL = {
    PRIORITY_NONE: 0,
    PRIORITY_HIGH: 1,
    PRIORITY_MEDIUM: 5,
    PRIORITY_LOW: 9,
}


def _ical_priority_to_canonical(value: Optional[int]) -> int:
    if not value:
        return PRIORITY_NONE
    if value <= 4:
        return PRIORITY_HIGH
    if value == 5:
        return PRIORITY_MEDIUM
    return PRIORITY_LOW


def _coerce_dt(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    return None


class RemindersConnector(Connector):
    def __init__(self, name: str, settings: dict):
        super().__init__(name, settings)
        self._client = None
        self._calendar = None
        self.list_name = settings.get("list_name", "Reminders")
        self.url = settings.get("url", ICLOUD_CALDAV_URL)

    # -- connection ----------------------------------------------------------

    @property
    def client(self):
        if self._client is None:
            import caldav

            self._client = caldav.DAVClient(
                url=self.url,
                username=self.settings["username"],
                password=self.settings["app_password"],
            )
        return self._client

    @property
    def calendar(self):
        if self._calendar is None:
            principal = self.client.principal()
            for cal in principal.calendars():
                name = (cal.name or "").strip()
                if name.lower() == self.list_name.lower():
                    self._calendar = cal
                    break
            if self._calendar is None:
                raise RuntimeError(
                    f"Reminders list {self.list_name!r} not found in iCloud account"
                )
        return self._calendar

    # -- mapping -------------------------------------------------------------

    def _to_task(self, todo) -> Task:
        comp = todo.icalendar_component
        status = str(comp.get("status", "")).upper()
        done = status == "COMPLETED" or comp.get("completed") is not None

        due = None
        if comp.get("due") is not None:
            due = _coerce_dt(comp.get("due").dt)

        updated = None
        if comp.get("last-modified") is not None:
            updated = _coerce_dt(comp.get("last-modified").dt)

        priority = None
        if comp.get("priority") is not None:
            priority = int(comp.get("priority"))

        return Task(
            title=str(comp.get("summary", "")),
            notes=str(comp.get("description", "")),
            done=done,
            due=due,
            priority=_ical_priority_to_canonical(priority),
            external_id=str(comp.get("uid")),
            updated_at=updated,
            raw={},
        )

    def _build_vtodo(self, task: Task, uid: Optional[str] = None) -> str:
        from icalendar import Calendar, Todo

        cal = Calendar()
        cal.add("prodid", "-//tasksync//EN")
        cal.add("version", "2.0")

        todo = Todo()
        if uid:
            todo.add("uid", uid)
        todo.add("summary", task.title or "(untitled)")
        if task.notes:
            todo.add("description", task.notes)
        if task.due is not None:
            todo.add("due", task.due)
        ical_priority = _PRIORITY_TO_ICAL.get(task.priority, 0)
        if ical_priority:
            todo.add("priority", ical_priority)
        if task.done:
            todo.add("status", "COMPLETED")
            todo.add("completed", datetime.now(timezone.utc))
            todo.add("percent-complete", 100)
        else:
            todo.add("status", "NEEDS-ACTION")
        todo.add("dtstamp", datetime.now(timezone.utc))
        todo.add("last-modified", datetime.now(timezone.utc))
        cal.add_component(todo)
        return cal.to_ical().decode("utf-8")

    def _todo_by_uid(self, uid: str):
        return self.calendar.todo_by_uid(uid)

    # -- CRUD ----------------------------------------------------------------

    def list_tasks(self) -> list[Task]:
        todos = self.calendar.todos(include_completed=True)
        return [self._to_task(t) for t in todos]

    def create_task(self, task: Task) -> str:
        import uuid

        uid = str(uuid.uuid4())
        self.calendar.save_todo(self._build_vtodo(task, uid=uid))
        return uid

    def update_task(self, external_id: str, task: Task) -> None:
        todo = self._todo_by_uid(external_id)
        todo.data = self._build_vtodo(task, uid=external_id)
        todo.save()

    def delete_task(self, external_id: str) -> None:
        self._todo_by_uid(external_id).delete()
