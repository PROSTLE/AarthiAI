"""
config/__init__.py
Centralised config loader — reads thresholds.yaml + secrets.yaml once,
exposes typed dicts everywhere in the codebase.
"""
import yaml
import os
from pathlib import Path

_BASE = Path(__file__).parent

def _load(name: str) -> dict:
    p = _BASE / name
    if not p.exists():
        return {}
    with open(p, "r") as f:
        return yaml.safe_load(f) or {}

CFG     = _load("thresholds.yaml")
SECRETS = _load("secrets.yaml") or _load("secrets.template.yaml")

# ── Shorthand accessors ───────────────────────────────────────────────────────
INTRADAY    = CFG.get("intraday", {})
SWING       = CFG.get("swing", {})
POSITIONAL  = CFG.get("positional", {})
CONFIDENCE  = CFG.get("confidence", {})
RISK        = CFG.get("risk", {})
SECTOR      = CFG.get("sector_heat", {})
SENTIMENT   = CFG.get("sentiment", {})
BEHAVIORAL  = CFG.get("behavioral", {})
MARKET      = CFG.get("market", {})
