import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from storage.manual_audit import read_manual_actions, record_manual_action


def test_manual_audit_records_and_reads_latest_first(tmp_path):
    audit_file = tmp_path / "manual_actions.jsonl"

    first = record_manual_action({"action": "modify", "ticket": 1, "status": "success"}, audit_file=audit_file)
    second = record_manual_action({"action": "close", "ticket": 2, "status": "failed", "error": "nope"}, audit_file=audit_file)

    items = read_manual_actions(limit=10, audit_file=audit_file)

    assert len(items) == 2
    assert items[0]["ticket"] == second["ticket"]
    assert items[0]["status"] == "failed"
    assert items[1]["ticket"] == first["ticket"]
    assert "timestamp" in items[0]


def test_manual_audit_skips_invalid_lines(tmp_path):
    audit_file = tmp_path / "manual_actions.jsonl"
    audit_file.write_text("bad json\n{\"ticket\":3,\"status\":\"success\"}\n", encoding="utf-8")

    items = read_manual_actions(limit=10, audit_file=audit_file)

    assert items == [{"ticket": 3, "status": "success"}]
