"""Load and validate YAML config, with ``${ENV_VAR}`` expansion.

Keeping secrets in environment variables (referenced from the YAML) means
``config.yaml`` itself stays safe to read and never needs real tokens in it.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        def repl(m: re.Match) -> str:
            name = m.group(1)
            if name not in os.environ:
                raise KeyError(f"Environment variable {name} referenced in config is not set")
            return os.environ[name]

        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


@dataclass
class Config:
    systems: dict[str, dict] = field(default_factory=dict)
    state_db: str = ".tasksync_state.db"
    interval_seconds: int = 300
    propagate_deletes: bool = True

    @property
    def enabled_systems(self) -> dict[str, dict]:
        return {
            name: cfg
            for name, cfg in self.systems.items()
            if cfg.get("enabled", True)
        }


def load_config(path: str) -> Config:
    import yaml

    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    data = _expand(data)
    sync = data.get("sync", {})
    return Config(
        systems=data.get("systems", {}),
        state_db=sync.get("state_db", ".tasksync_state.db"),
        interval_seconds=int(sync.get("interval_seconds", 300)),
        propagate_deletes=bool(sync.get("propagate_deletes", True)),
    )
