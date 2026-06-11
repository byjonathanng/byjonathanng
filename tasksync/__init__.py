"""tasksync — keep tasks in sync across Jira, Trello and iOS Reminders.

A small hub-and-spoke sync engine. Each external system is a *connector*
that exposes a uniform interface (list/create/update/delete) over a
canonical :class:`~tasksync.model.Task`. A SQLite state store remembers
which task in one system corresponds to which in the others, so the engine
can tell what actually changed and resolve conflicts with last-write-wins.
"""

__version__ = "0.1.0"
