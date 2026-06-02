import json
import time
from pathlib import Path
from typing import Any, Dict, List


AUDIT_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "manual_actions.jsonl"


def record_manual_action(entry: Dict[str, Any], audit_file: Path = AUDIT_FILE) -> Dict[str, Any]:
    audit_file = Path(audit_file)
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": time.time(),
        **entry,
    }
    with audit_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")
    return row


def read_manual_actions(limit: int = 100, audit_file: Path = AUDIT_FILE) -> List[Dict[str, Any]]:
    audit_file = Path(audit_file)
    if not audit_file.exists():
        return []
    limit = max(1, min(int(limit or 100), 1000))
    lines = audit_file.read_text(encoding="utf-8").splitlines()
    items: List[Dict[str, Any]] = []
    for line in reversed(lines[-limit:]):
        try:
            data = json.loads(line)
        except Exception:
            continue
        if isinstance(data, dict):
            items.append(data)
    return items
