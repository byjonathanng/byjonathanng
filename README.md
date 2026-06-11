# tasksync

Keep your tasks in sync across **Jira**, **Trello**, and the **iOS Reminders**
app. One task, edited anywhere, shows up everywhere.

It's a small hub-and-spoke sync engine: each system is a *connector* exposing
a uniform interface over a neutral task model, and a SQLite *state store*
remembers which task in one system corresponds to which in the others. That
memory is what lets it tell a brand-new task from an edit, resolve conflicts,
and avoid re-creating duplicate copies on every run.

```
   Jira  ◄──┐                 ┌──►  Trello
            │                 │
         ┌──┴─────────────────┴──┐
         │   tasksync engine      │   canonical Task model
         │   + SQLite state store │   "which task == which" + last-synced hash
         └──┬─────────────────────┘
            │
   iOS Reminders  (iCloud CalDAV)
```

## Why CalDAV for Reminders?

Jira and Trello have clean REST APIs. **iOS Reminders has no public cloud
API** — but iCloud exposes every Reminders list as a CalDAV calendar of
`VTODO` items. That's the only way to read/write Reminders from an unattended
server, and it's exactly what apps like Fantastical and 2Do use. You connect
with your Apple ID email and an **app-specific password**; changes appear on
every device signed into the same iCloud account.

## How syncing works

On each run the engine:

1. **Pulls** every task from every enabled system.
2. **Classifies** each one against the state store: *new*, *changed* (content
   hash differs), *unchanged*, or *deleted* (a task it knew about that's gone).
3. **Clusters** tasks that are the same thing across systems. New tasks with
   identical titles are merged into one cluster so the first run reconciles
   existing duplicates instead of cross-creating copies.
4. **Picks a winner** per cluster — the most recently modified change (or a
   deletion) — and **propagates** it to the other systems.
5. **Records** new hashes so the next run starts from a clean baseline.

**Conflict policy:** last-write-wins by modification time. Deletions are
timestamped "now", so an intentional delete generally beats a stale edit
elsewhere. (Deletes only propagate if `propagate_deletes: true`.)

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml      # then edit it
```

Edit `config.yaml` and provide the secrets via environment variables (the YAML
references them as `${VAR}` so the file stays safe to keep around).

### Credentials you'll need

| System | What | Where to get it |
|---|---|---|
| Jira | API token + your account email | id.atlassian.com → Security → **API tokens** |
| Trello | API key + token | trello.com/app-key (generate a token from that page) |
| Reminders | Apple ID email + **app-specific password** | appleid.apple.com → Sign-In and Security → **App-Specific Passwords** |

Finding the **Trello `list_id`**: open the board, append `.json` to the URL,
and search for the list's `id`. Finding the **Reminders `list_name`**: it's
just the name of the list as it appears in the Reminders app (default
`Reminders`).

```bash
export JIRA_EMAIL=you@example.com
export JIRA_API_TOKEN=...
export TRELLO_API_KEY=...
export TRELLO_TOKEN=...
export ICLOUD_EMAIL=you@icloud.com
export ICLOUD_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

## Usage

```bash
# Check that every enabled connector actually connects:
python3 -m tasksync doctor

# Preview what would change — writes nothing:
python3 -m tasksync sync --dry-run

# Do a real sync pass:
python3 -m tasksync sync

# Run continuously on the configured interval (default 5 min):
python3 -m tasksync sync --loop

# Inspect what the state store knows:
python3 -m tasksync status
```

Use `-c path/to/config.yaml` to point at a different config, and `-v` for
verbose logging.

### Running it on a schedule

Cron, every 5 minutes:

```cron
*/5 * * * * cd /path/to/tasksync && /path/to/.venv/bin/python -m tasksync sync >> sync.log 2>&1
```

Or keep `tasksync sync --loop` running under systemd / `tmux` / a container.

## What gets synced

| Field | Jira | Trello | Reminders |
|---|---|---|---|
| Title | summary | card name | summary |
| Notes | description | card description | notes |
| Done | status category *done* | due-complete flag | completed |
| Due date | due date | card due | due |
| Priority | priority | — (not native) | priority |

Completion is mapped to each system's native notion (a Jira transition, a
Trello "due complete", a Reminders completed flag) rather than moving cards or
issues between columns.

## Configuration reference

See [`config.example.yaml`](config.example.yaml). Highlights:

- `sync.propagate_deletes` — delete in one system → delete in the others.
- `sync.interval_seconds` — used by `sync --loop`.
- `jira.jql` — controls which issues participate (default: the whole project).
- `jira.delete_mode` — `done` (transition to done) or `delete` (remove issue).
- `trello.delete_mode` — `archive` or `delete`.
- Set `enabled: false` on any system to sync just the other two.

## First-run advice

The engine merges same-titled tasks to avoid duplicating things that already
exist in two places, but matching by title isn't perfect. For the cleanest
start, either begin with one populated system and empty others, or run
`sync --dry-run` first and eyeball the planned changes.

## Development

```bash
pip install -r requirements.txt
pytest
```

The engine is tested end-to-end through an in-memory connector
(`tests/memory_connector.py`), so the sync logic — create/update/complete/
delete propagation, idempotency, duplicate-merging, dry-run — is verified
without touching any network.

## Project layout

```
tasksync/
  model.py            canonical Task + content hashing
  state.py            SQLite state store (cross-system links + clusters)
  engine.py           the sync algorithm
  config.py           YAML loading with ${ENV} expansion
  cli.py              sync / doctor / status commands
  connectors/
    base.py           the connector interface
    jira.py           Jira REST (jira SDK)
    trello.py         Trello REST (py-trello)
    reminders.py      iOS Reminders via iCloud CalDAV
```

Adding another system (Asana, Todoist, Google Tasks, …) is just a new
connector implementing `list/create/update/delete` over the `Task` model.
