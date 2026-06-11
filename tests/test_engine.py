"""End-to-end engine behaviour, exercised through in-memory connectors."""

from __future__ import annotations

import os
import tempfile
import time

import pytest

from tasksync.engine import SyncEngine
from tasksync.model import Task
from tasksync.state import StateStore
from tests.memory_connector import MemoryConnector


@pytest.fixture()
def state_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    os.unlink(path)


def make_engine(state_path, **connectors):
    state = StateStore(state_path)
    engine = SyncEngine(connectors, state)
    return engine, state


def titles(connector):
    return sorted(t.title for t in connector.list_tasks())


def test_new_task_propagates_to_all_systems(state_path):
    jira = MemoryConnector("jira")
    trello = MemoryConnector("trello")
    reminders = MemoryConnector("reminders")
    jira.seed(Task(title="Write report"))

    engine, state = make_engine(state_path, jira=jira, trello=trello, reminders=reminders)
    report = engine.sync()
    state.close()

    assert titles(trello) == ["Write report"]
    assert titles(reminders) == ["Write report"]
    assert any(c.action == "create" for c in report.changes)


def test_no_duplicates_on_second_run(state_path):
    jira = MemoryConnector("jira")
    trello = MemoryConnector("trello")
    jira.seed(Task(title="Buy milk"))

    engine, state = make_engine(state_path, jira=jira, trello=trello)
    engine.sync()
    second = engine.sync()
    state.close()

    assert titles(trello) == ["Buy milk"]
    assert len(jira.list_tasks()) == 1
    assert second.changes == []  # idempotent


def test_edit_propagates_with_last_write_wins(state_path):
    jira = MemoryConnector("jira")
    trello = MemoryConnector("trello")
    jid = jira.seed(Task(title="Draft"))

    engine, state = make_engine(state_path, jira=jira, trello=trello)
    engine.sync()  # both now have "Draft"

    # Edit on the Jira side.
    time.sleep(0.01)
    jira.tasks[jid].title = "Final draft"
    jira.tasks[jid].updated_at = __import__("tasksync.model", fromlist=["utcnow"]).utcnow()

    engine.sync()
    state.close()

    assert titles(trello) == ["Final draft"]


def test_completion_syncs(state_path):
    jira = MemoryConnector("jira")
    trello = MemoryConnector("trello")
    jid = jira.seed(Task(title="Task A"))

    engine, state = make_engine(state_path, jira=jira, trello=trello)
    engine.sync()

    from tasksync.model import utcnow
    jira.tasks[jid].done = True
    jira.tasks[jid].updated_at = utcnow()
    engine.sync()
    state.close()

    assert all(t.done for t in trello.list_tasks())


def test_delete_propagates(state_path):
    jira = MemoryConnector("jira")
    trello = MemoryConnector("trello")
    jid = jira.seed(Task(title="Temp"))

    engine, state = make_engine(state_path, jira=jira, trello=trello)
    engine.sync()
    assert len(trello.list_tasks()) == 1

    del jira.tasks[jid]
    engine.sync()
    state.close()

    assert trello.list_tasks() == []


def test_identical_titles_merge_into_one_cluster(state_path):
    # Both systems already have the "same" task; first sync should reconcile
    # them rather than cross-create duplicates.
    jira = MemoryConnector("jira")
    trello = MemoryConnector("trello")
    jira.seed(Task(title="Standup"))
    trello.seed(Task(title="standup"))  # different case, same task

    engine, state = make_engine(state_path, jira=jira, trello=trello)
    engine.sync()
    state.close()

    assert len(jira.list_tasks()) == 1
    assert len(trello.list_tasks()) == 1


def test_dry_run_writes_nothing(state_path):
    jira = MemoryConnector("jira")
    trello = MemoryConnector("trello")
    jira.seed(Task(title="Ghost"))

    state = StateStore(state_path)
    engine = SyncEngine({"jira": jira, "trello": trello}, state, dry_run=True)
    report = engine.sync()
    state.close()

    assert trello.list_tasks() == []  # nothing created
    assert any(c.action == "create" for c in report.changes)  # but reported
