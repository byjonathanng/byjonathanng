"""Command line interface for tasksync.

    tasksync sync [--dry-run]      run one sync pass
    tasksync sync --loop           run forever on the configured interval
    tasksync doctor                check that every enabled connector connects
    tasksync status                show what the state store currently knows
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from .config import Config, load_config
from .connectors import build_connector
from .engine import SyncEngine
from .state import StateStore


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


def _build_connectors(config: Config) -> dict:
    connectors = {}
    for name, cfg in config.enabled_systems.items():
        connectors[name] = build_connector(name, cfg)
    return connectors


def _cmd_sync(config: Config, args: argparse.Namespace) -> int:
    connectors = _build_connectors(config)
    if len(connectors) < 2:
        print("Need at least two enabled systems to sync.", file=sys.stderr)
        return 2

    def run_once() -> None:
        state = StateStore(config.state_db)
        try:
            engine = SyncEngine(
                connectors,
                state,
                dry_run=args.dry_run,
                propagate_deletes=config.propagate_deletes,
            )
            report = engine.sync()
            prefix = "[dry-run] " if args.dry_run else ""
            for change in report.changes:
                print(f"{prefix}{change.action:6} {change.system:10} {change.title}")
            for err in report.errors:
                print(f"{prefix}ERROR  {err}", file=sys.stderr)
            print(f"{prefix}{report.summary()}")
        finally:
            state.close()

    if not args.loop:
        run_once()
        return 0

    print(f"Looping every {config.interval_seconds}s. Ctrl-C to stop.")
    try:
        while True:
            run_once()
            time.sleep(config.interval_seconds)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def _cmd_doctor(config: Config, args: argparse.Namespace) -> int:
    connectors = _build_connectors(config)
    if not connectors:
        print("No systems enabled in config.", file=sys.stderr)
        return 2
    ok = True
    for name, connector in connectors.items():
        try:
            tasks = connector.list_tasks()
            print(f"OK    {name:10} reachable ({len(tasks)} task(s))")
        except Exception as exc:
            ok = False
            print(f"FAIL  {name:10} {exc}")
    return 0 if ok else 1


def _cmd_status(config: Config, args: argparse.Namespace) -> int:
    state = StateStore(config.state_db)
    try:
        links = state.all_links()
        clusters = state.cluster_members(links)
        active = [c for c in clusters.values() if any(not l.deleted for l in c.values())]
        print(f"State DB: {config.state_db}")
        print(f"Clusters: {len(active)} active / {len(clusters)} total")
        print(f"Links:    {len([l for l in links if not l.deleted])} active / {len(links)} total")
        for cid, members in sorted(clusters.items()):
            systems = ", ".join(
                f"{s}:{l.external_id}" for s, l in members.items() if not l.deleted
            )
            if systems:
                print(f"  {cid}  {systems}")
    finally:
        state.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tasksync", description=__doc__)
    parser.add_argument("-c", "--config", default="config.yaml", help="path to config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="run a sync pass")
    p_sync.add_argument("--dry-run", action="store_true", help="show changes, write nothing")
    p_sync.add_argument("--loop", action="store_true", help="run forever on the interval")
    p_sync.set_defaults(func=_cmd_sync)

    sub.add_parser("doctor", help="check connector connectivity").set_defaults(func=_cmd_doctor)
    sub.add_parser("status", help="show state store contents").set_defaults(func=_cmd_status)

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        print(
            f"Config not found: {args.config}\n"
            "Copy config.example.yaml to config.yaml and fill it in.",
            file=sys.stderr,
        )
        return 2
    except KeyError as exc:
        print(f"Config error: {exc.args[0]}", file=sys.stderr)
        return 2
    return args.func(config, args)


if __name__ == "__main__":
    raise SystemExit(main())
