"""Connectors translate each external system to the canonical Task model."""

from .base import Connector

__all__ = ["Connector", "build_connector"]


def build_connector(name: str, settings: dict) -> Connector:
    """Instantiate a connector by system name from its config block.

    Imports are lazy so that, e.g., not having ``caldav`` installed only
    matters if you actually enable the Reminders connector.
    """
    if name == "jira":
        from .jira import JiraConnector

        return JiraConnector(name, settings)
    if name == "trello":
        from .trello import TrelloConnector

        return TrelloConnector(name, settings)
    if name == "reminders":
        from .reminders import RemindersConnector

        return RemindersConnector(name, settings)
    raise ValueError(f"Unknown connector: {name!r}")
