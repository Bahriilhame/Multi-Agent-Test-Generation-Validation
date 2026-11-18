"""Read and summarize the generic workflow's append-only event log."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

NODE_LABELS = {
    "analyze": "Analyse du projet et couverture initiale",
    "generator": "Génération des tests avec Ollama",
    "validation": "Exécution des tests dans Docker",
    "critic": "Évaluation de la qualité des tests",
    "retry": "Préparation de l’itération suivante",
    "finalize": "Création du rapport final",
}


def read_events(path: Path) -> list[dict[str, Any]]:
    """Return valid JSONL events; tolerate a partially written final line."""
    if not path.is_file():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("node") in NODE_LABELS:
            events.append(event)
    return events


def summarize_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse started/completed pairs into one row per node and iteration."""
    steps: dict[tuple[str, int], dict[str, Any]] = {}
    for event in events:
        node = event["node"]
        iteration = int(event.get("iteration", 0))
        key = (node, iteration)
        step = steps.setdefault(key, {
            "node": node,
            "label": NODE_LABELS[node],
            "iteration": iteration,
            "status": "pending",
            "started_at": None,
            "finished_at": None,
            "error": None,
        })
        status = event.get("status")
        if status == "started":
            step["status"] = "running"
            step["started_at"] = event.get("timestamp")
        elif status in {"completed", "failed"}:
            step["status"] = status
            step["finished_at"] = event.get("timestamp")
            step["error"] = event.get("error")
    return list(steps.values())
