"""Jira connector (REST via the official ``jira`` SDK).

Tasks map to issues returned by a configurable JQL query. Completion is
detected from the issue's status *category* ("done"), and applied by
transitioning the issue to a configured done/reopen status.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from ..model import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    PRIORITY_NONE,
    Task,
)
from .base import Connector

# Canonical priority -> Jira priority name (override via config["priority_map"]).
_DEFAULT_PRIORITY_TO_JIRA = {
    PRIORITY_HIGH: "High",
    PRIORITY_MEDIUM: "Medium",
    PRIORITY_LOW: "Low",
}
_JIRA_NAME_TO_PRIORITY = {
    "highest": PRIORITY_HIGH,
    "high": PRIORITY_HIGH,
    "medium": PRIORITY_MEDIUM,
    "low": PRIORITY_LOW,
    "lowest": PRIORITY_LOW,
}


class JiraConnector(Connector):
    def __init__(self, name: str, settings: dict):
        super().__init__(name, settings)
        self._client = None
        self.project = settings["project"]
        self.issue_type = settings.get("issue_type", "Task")
        self.jql = settings.get(
            "jql", f'project = "{self.project}" ORDER BY updated DESC'
        )
        self.done_status = settings.get("done_status", "Done")
        self.reopen_status = settings.get("reopen_status", "To Do")
        self.delete_mode = settings.get("delete_mode", "done")  # done | delete
        self.priority_to_jira = {
            **_DEFAULT_PRIORITY_TO_JIRA,
            **settings.get("priority_map", {}),
        }

    # -- connection ----------------------------------------------------------

    @property
    def client(self):
        if self._client is None:
            from jira import JIRA

            self._client = JIRA(
                server=self.settings["server"],
                basic_auth=(self.settings["email"], self.settings["api_token"]),
            )
        return self._client

    # -- mapping -------------------------------------------------------------

    def _to_task(self, issue) -> Task:
        fields = issue.fields
        done = False
        status = getattr(fields, "status", None)
        if status is not None:
            category = getattr(status, "statusCategory", None)
            key = getattr(category, "key", "") if category else ""
            done = key == "done"

        priority = PRIORITY_NONE
        if getattr(fields, "priority", None) is not None:
            priority = _JIRA_NAME_TO_PRIORITY.get(
                fields.priority.name.lower(), PRIORITY_NONE
            )

        due: Optional[datetime] = None
        if getattr(fields, "duedate", None):
            try:
                due = datetime.fromisoformat(fields.duedate)
            except ValueError:
                due = None

        return Task(
            title=fields.summary or "",
            notes=getattr(fields, "description", None) or "",
            done=done,
            due=due,
            priority=priority,
            external_id=issue.key,
            updated_at=datetime.fromisoformat(fields.updated) if fields.updated else None,
            raw={"status": getattr(status, "name", None)},
        )

    def _fields_for(self, task: Task) -> dict:
        fields = {"summary": task.title or "(untitled)"}
        if task.notes:
            fields["description"] = task.notes
        if task.due is not None:
            fields["duedate"] = task.due.date().isoformat()
        jira_priority = self.priority_to_jira.get(task.priority)
        if jira_priority:
            fields["priority"] = {"name": jira_priority}
        return fields

    # -- CRUD ----------------------------------------------------------------

    def list_tasks(self) -> list[Task]:
        issues = self.client.search_issues(self.jql, maxResults=False)
        return [self._to_task(i) for i in issues]

    def create_task(self, task: Task) -> str:
        fields = self._fields_for(task)
        fields["project"] = {"key": self.project}
        fields["issuetype"] = {"name": self.issue_type}
        issue = self.client.create_issue(fields=fields)
        if task.done:
            self._transition_to(issue, self.done_status)
        return issue.key

    def update_task(self, external_id: str, task: Task) -> None:
        issue = self.client.issue(external_id)
        issue.update(fields=self._fields_for(task))
        # Reconcile completion state.
        category = getattr(issue.fields.status.statusCategory, "key", "")
        currently_done = category == "done"
        if task.done and not currently_done:
            self._transition_to(issue, self.done_status)
        elif not task.done and currently_done:
            self._transition_to(issue, self.reopen_status)

    def delete_task(self, external_id: str) -> None:
        if self.delete_mode == "delete":
            self.client.issue(external_id).delete()
        else:
            self._transition_to(self.client.issue(external_id), self.done_status)

    # -- helpers -------------------------------------------------------------

    def _transition_to(self, issue, status_name: str) -> None:
        wanted = status_name.lower()
        for t in self.client.transitions(issue):
            if t["name"].lower() == wanted or t["to"]["name"].lower() == wanted:
                self.client.transition_issue(issue, t["id"])
                return
        # No matching transition available from the current status; leave as-is.
