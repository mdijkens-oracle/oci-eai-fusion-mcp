"""Author: M. Dijkens. Workflow catalog shared by the UI and MCP tools."""
import json
import re
from pathlib import Path

def load_catalog(settings, filename=None):
    data = json.loads(Path(filename or Path(__file__).with_name("agents.json")).read_text(encoding="utf-8-sig"))
    entries, names = [], set()
    for entry in data["agents"]:
        name = entry["tool"]
        workflow = entry.get("workflow") or settings.get(entry.get("workflow_env", ""))
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,63}", name) or name in names:
            raise ValueError("Invalid or duplicate catalog tool name.")
        if not workflow or not entry.get("description"):
            raise ValueError("Catalog workflow or description is missing.")
        names.add(name)
        entries.append({**entry, "workflow": workflow})
    if not entries: raise ValueError("At least one agent must be configured.")
    return entries

