"""Project-wide constants and the run configuration.

Every tunable knob lives in ``configs/default.json`` so that a run can be
reproduced from a single file; this module only holds facts about the
dataset itself (label spellings, identifier columns) and the loader for the
JSON configuration.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

LABEL_COL = "Label"
BENIGN = "Benign"

# Spellings are verbatim from the CSE-CIC-IDS2018 CSVs (including the
# dataset's own "Infilteration" typo and inconsistent DoS/DDOS casing).
LABELS = [
    "Benign",
    "FTP-BruteForce",
    "SSH-Bruteforce",
    "DoS attacks-GoldenEye",
    "DoS attacks-Slowloris",
    "DoS attacks-Hulk",
    "DoS attacks-SlowHTTPTest",
    "DDoS attacks-LOIC-HTTP",
    "DDOS attack-HOIC",
    "DDOS attack-LOIC-UDP",
    "Brute Force -Web",
    "Brute Force -XSS",
    "SQL Injection",
    "Infilteration",
    "Bot",
]

# Identifier / time columns. They identify a host or a moment in the capture
# rather than describing the flow's behaviour, so a model that uses them
# learns the testbed (which IP attacked on which day), not the attack.
ID_COLUMNS = ["Flow ID", "Src IP", "Src Port", "Dst IP", "Timestamp"]

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "default.json"


def _deep_update(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def load_config(path: str | Path | None = None, overrides: dict | None = None) -> dict:
    """Load the default config, then layer an optional file and overrides on top."""
    with open(DEFAULT_CONFIG_PATH, encoding="utf-8") as fh:
        cfg = json.load(fh)
    if path is not None and Path(path).resolve() != DEFAULT_CONFIG_PATH.resolve():
        with open(path, encoding="utf-8") as fh:
            _deep_update(cfg, json.load(fh))
    if overrides:
        _deep_update(cfg, deepcopy(overrides))
    return cfg


def resolve(path: str | Path) -> Path:
    """Resolve a config path relative to the project root."""
    p = Path(path)
    return p if p.is_absolute() else PROJECT_ROOT / p
