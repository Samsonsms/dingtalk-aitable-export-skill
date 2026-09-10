"""Explicitly authorized live single-table export; writes private local evidence."""

import argparse
from datetime import datetime
import importlib.util
import json
import subprocess
import uuid

from project_checks import ROOT, SKILL, VERSION, source_digest

SPEC = importlib.util.spec_from_file_location("export_table", SKILL / "scripts/export_table.py")
export_table = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(export_table)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--table", required=True, help="Previously selected exact table name or ID")
    parser.add_argument("--profile")
    arguments = parser.parse_args()
    client = export_table.Dws(arguments.profile)
    catalog_path = ROOT / "tmp" / ("smoke_catalog_" + uuid.uuid4().hex[:8] + ".json")
    export_table.list_catalog(client, export_table.base_from_env(arguments.env_file), catalog_path)
    exporter = export_table.prepare(client, export_table.read_json(catalog_path), arguments.table, ROOT / "output/dingtalk_exports")
    state = exporter.state
    before = client.call("aitable", "view", "list", "--base-id", state["baseId"], "--table-id", state["tableId"])["data"]["views"]
    with export_table.StateLock(exporter.state_path):
        result = exporter.proceed()
    after = client.call("aitable", "view", "list", "--base-id", state["baseId"], "--table-id", state["tableId"])["data"]["views"]
    checks = result["verification"]
    formula_values = sum(column["nonemptyValues"] for column in checks["computedColumns"] if column["type"] == "formula")
    reference_values = sum(column["nonemptyValues"] for column in checks["computedColumns"] if column["type"] != "formula")
    existing_unchanged = sorted(before, key=lambda view: view["viewId"]) == sorted(after, key=lambda view: view["viewId"])
    if not existing_unchanged or not formula_values or not reference_values:
        raise RuntimeError("Smoke fixture must exercise formula/reference values and preserve existing views")
    # Exercise completed-state resume against real artifact bytes without another export.
    replay = exporter.proceed()
    if replay != result:
        raise RuntimeError("Completed resume is not idempotent")
    dws_version = subprocess.run(client.prefix + ["--version"], capture_output=True, encoding="utf-8", timeout=30, check=True).stdout.strip()
    evidence = {"status": "passed", "version": VERSION, "sourceDigest": source_digest(),
                "testedAt": datetime.now().astimezone().isoformat(), "dwsVersion": dws_version,
                "file": result["file"], "state": str(exporter.state_path),
                "checks": {"sheetCount": checks["sheetCount"], "columns": checks["columns"], "dataRows": checks["dataRows"],
                           "headerFill": checks["headerFill"], "headerBorders": checks["headerBorders"],
                           "bytesUnchanged": checks["bytesUnchanged"], "viewDeleted": result["viewDeleted"],
                           "existingViewsUnchanged": existing_unchanged, "formulaValues": formula_values,
                           "referenceValues": reference_values, "idempotentResume": True,
                           "sourceErrorCount": len(checks["sourceErrors"]), "sha256": checks["sha256"]}}
    export_table.write_json(ROOT / "tmp/live_smoke.json", evidence)
    print(json.dumps(evidence, ensure_ascii=False))


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    main()
