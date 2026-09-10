"""Export one selected DingTalk table through official DWS; never author XLSX."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import zipfile

VERSION = "1.0.0"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class ExportError(Exception):
    """A safe, user-visible failure; never contains raw CLI or download output."""


class Pending(ExportError):
    pass


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def base_from_env(path):
    entries = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        match = re.match(r"^\s*(?:export\s+)?(DINGTALK_BASE_ID|baseId)\s*=\s*(.*?)\s*$", line)
        if not match:
            continue
        value = match[2]
        if value[:1] in ("'", '"'):
            quoted = re.fullmatch(r"(['\"])(.*?)\1\s*(?:#.*)?", value)
            if not quoted:
                raise ExportError("Invalid base ID quoting in env file")
            value = quoted[2]
        else:
            value = re.split(r"\s+#", value)[0].strip()
        entries.append((match[1], value))
    if not entries or len({key for key, _ in entries}) != len(entries):
        raise ExportError("Missing or duplicated base ID in env file")
    values = {value for _, value in entries}
    if len(values) != 1:
        raise ExportError("DINGTALK_BASE_ID and baseId conflict")
    value = values.pop()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value) or value == "YOUR_BASE_ID":
        raise ExportError("Empty, placeholder, or invalid base ID")
    return value


def dws_prefix():
    executable = shutil.which("dws.exe")
    if executable:
        return [executable]
    shim = shutil.which("dws.cmd") if os.name == "nt" else shutil.which("dws")
    if shim and os.name != "nt":
        return [shim]
    if shim:
        wrapper = Path(shim).parent / "node_modules/dingtalk-workspace-cli/bin/dws.js"
        node = shutil.which("node.exe")
        if wrapper.is_file() and node:
            # Invoke the official npm entry point without cmd.exe interpolation.
            return [node, str(wrapper)]
    raise ExportError("DWS not found: npm install -g dingtalk-workspace-cli")


class Dws:
    def __init__(self, profile=None):
        self.profile = profile
        self.prefix = dws_prefix()

    def call(self, *arguments, allow_timeout=False):
        command = self.prefix + list(arguments) + ["--format", "json"]
        if self.profile:
            command += ["--profile", self.profile]
        try:
            completed = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", timeout=90)
        except subprocess.TimeoutExpired as exc:
            raise ExportError("CLI_PROCESS_TIMEOUT: operation outcome unknown; do not replay writes") from exc
        payload = None
        for stream in (completed.stdout, completed.stderr):
            try:
                candidate = json.loads(stream)
                if isinstance(candidate, dict):
                    payload = candidate
                    break
            except (ValueError, TypeError):
                continue
        if payload is None:
            raise ExportError("CLI_INVALID_JSON: inspect DWS locally; raw output suppressed")
        timeout_error = any(value == "TIMEOUT_ERROR" for value in flatten(payload))
        if allow_timeout and timeout_error:
            return payload
        if completed.returncode or payload.get("success") is False or payload.get("status") in ("error", "failed") or payload.get("error"):
            error = payload.get("error") or {}
            code = error.get("reason") or error.get("category") or error.get("code") or "unknown"
            safe_code = re.sub(r"[^A-Za-z0-9_-]", "", str(code))[:80]
            raise ExportError(f"DWS_ERROR: {safe_code}; check auth/permissions with official DWS")
        return payload


def flatten(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from flatten(item)
    elif isinstance(value, list):
        for item in value:
            yield from flatten(item)
    else:
        yield value


def authenticated(client, expected=None):
    status = client.call("auth", "status")
    if status.get("authenticated") is not True or status.get("token_valid") is not True:
        raise ExportError("LOGIN_REQUIRED: dws auth login --device --recommend")
    identity = {key: status.get(key) for key in ("corp_id", "user_id")}
    if not all(identity.values()):
        raise ExportError("DWS did not return a unique organization/user identity")
    if expected and identity != expected:
        raise ExportError("Account mismatch; use the same profile as the saved catalog/state")
    profile = f"{identity['corp_id']}:{identity['user_id']}"
    if client.profile and client.profile != profile:
        raise ExportError("DWS returned a different identity from the requested profile")
    client.profile = profile
    return identity


def tables(client, base):
    payload = client.call("aitable", "+list-tables", "--base", base)
    result = payload.get("tables")
    if not isinstance(result, list) or payload.get("hasMore"):
        raise ExportError("Unexpected or incomplete table catalog")
    for row in result:
        if not row.get("tableId") or not isinstance(row.get("tableName"), str):
            raise ExportError("Invalid table entry")
    if len({row['tableId'] for row in result}) != len(result):
        raise ExportError("Duplicate table IDs")
    return [row for row in result if "测试" not in row["tableName"]]


def list_catalog(client, base, path):
    if Path(path).exists():
        raise ExportError("Catalog already exists; choose another path to preserve prior selection")
    if not client.profile:
        profiles = client.call("profile", "list").get("profiles", [])
        if not profiles:
            raise ExportError("LOGIN_REQUIRED: dws auth login --device --recommend")
        current = [row for row in profiles if row.get("isCurrent") is True and row.get("isOrgCurrent") is True]
        if len(current) != 1 or not current[0].get("profile"):
            raise ExportError("Choose an explicit organization/account with --profile; no unique current profile")
        client.profile = current[0]["profile"]
    identity = authenticated(client)
    catalog = {"version": VERSION, "baseId": base, "identity": identity, "profile": client.profile,
               "tables": tables(client, base), "createdAt": datetime.now().astimezone().isoformat()}
    write_json(path, catalog)
    return {"status": "selection_required", "catalog": str(Path(path).resolve()), "tables": catalog["tables"]}


def field_catalog(client, base, table):
    payload = client.call("aitable", "field", "list", "--base-id", base, "--table-id", table)
    data = payload.get("data", {})
    fields = data.get("fields")
    if not isinstance(fields, list) or not fields or data.get("hasMore"):
        raise ExportError("Missing or incomplete field catalog")
    result = [{key: field[key] for key in ("fieldId", "fieldName", "type")} for field in fields]
    if len({field['fieldId'] for field in result}) != len(result):
        raise ExportError("Duplicate field IDs")
    return result


def check_view(view, fields):
    columns = view.get("columns")
    if not isinstance(columns, list) or Counter(columns) != Counter(field["fieldId"] for field in fields):
        raise ExportError("Temporary view does not contain every field exactly once")
    filters = view.get("filter")
    if filters not in ({}, [], None) and filters != {"operands": [], "operator": "and"}:
        raise ExportError("Temporary view has filters")
    if view.get("sort") or view.get("group"):
        raise ExportError("Temporary view has sorting or grouping")
    hidden = view.get("custom", {}).get("hiddenFields", {})
    if not isinstance(hidden, dict) or any(hidden.values()):
        raise ExportError("Temporary view has hidden fields")
    if view.get("viewType") != "Grid":
        raise ExportError("Temporary view is not Grid")


def file_stem(name):
    result = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().rstrip(". ")[:120]
    if not result:
        result = "table"
    if re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", result, re.I):
        result = "_" + result
    return result


def download(url, path):
    if urlparse(url).scheme != "https":
        raise ExportError("Download URL must use HTTPS")
    curl = shutil.which("curl.exe")
    if not curl:
        raise ExportError("curl.exe missing; Windows curl is required")
    path = Path(path)
    if path.exists():
        raise ExportError("Refusing to overwrite an existing file")
    part = path.with_suffix(path.suffix + ".part")
    result = subprocess.run([curl, "-L", "--fail", "--silent", "--show-error", "--proto", "=https",
                             "--proto-redir", "=https", "--connect-timeout", "30", "--max-time", "300",
                             "-o", str(part), url], capture_output=True, timeout=315)
    if result.returncode:
        raise ExportError(f"DOWNLOAD_FAILED: curl exit {result.returncode}; partial file is not an Excel deliverable")
    part.replace(path)


def cell_value(cell, strings):
    if cell.get("t") == "inlineStr":
        return "".join(cell.itertext())
    value = cell.find("s:v", NS)
    if value is None:
        return None
    return strings[int(value.text)] if cell.get("t") == "s" else value.text


def column_number(reference):
    match = re.fullmatch(r"([A-Z]+)[0-9]+", reference)
    if not match:
        raise ExportError("Invalid XLSX cell reference")
    number = 0
    for letter in match[1]:
        number = number * 26 + ord(letter) - 64
    return number


def verify_xlsx(path, table_name, fields, column_ids):
    before = digest(path)
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise ExportError("XLSX ZIP integrity check failed")
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.findall("s:sheets/s:sheet", NS)
        if len(sheets) != 1 or sheets[0].get("name") != table_name:
            raise ExportError("Expected exactly one sheet with the selected table name")
        if sheets[0].get("state", "visible") != "visible":
            raise ExportError("Selected sheet is hidden")
        relation_id = sheets[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(item.get("Target") for item in relationships if item.get("Id") == relation_id)
        sheet_path = target.lstrip("/") if target.startswith("/") else "xl/" + target
        sheet = ET.fromstring(archive.read(sheet_path))
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            for item in ET.fromstring(archive.read("xl/sharedStrings.xml")):
                strings.append("".join(node.text or "" for node in item.iterfind(".//s:t", NS)))
        rows = sheet.findall("s:sheetData/s:row", NS)
        header = next((row for row in rows if row.get("r") == "1"), None)
        if header is None:
            raise ExportError("Missing header row")
        header_cells = header.findall("s:c", NS)
        field_by_id = {field["fieldId"]: field for field in fields}
        expected_headers = [field_by_id[field_id]["fieldName"] for field_id in column_ids]
        headers = [cell_value(cell, strings) for cell in header_cells]
        if headers != expected_headers or [column_number(cell.get("r", "")) for cell in header_cells] != list(range(1, len(fields) + 1)):
            raise ExportError("Header names/order/count do not match all temporary-view fields")
        if any(column_number(cell.get("r", "")) > len(fields) for row in rows for cell in row):
            raise ExportError("Unexpected extra data columns")
        styles = ET.fromstring(archive.read("xl/styles.xml"))
        formats = styles.find("s:cellXfs", NS)
        fills = styles.find("s:fills", NS)
        borders = styles.find("s:borders", NS)
        for cell in header_cells:
            style = formats[int(cell.get("s", "0"))]
            fill = fills[int(style.get("fillId", "0"))].find("s:patternFill", NS)
            border = borders[int(style.get("borderId", "0"))]
            if fill is None or fill.get("patternType") != "solid":
                raise ExportError("Header fill missing")
            if any(border.find("s:" + side, NS) is None or not border.find("s:" + side, NS).get("style") for side in ("left", "right", "top", "bottom")):
                raise ExportError("Header border missing")
        nonempty = Counter()
        errors = []
        data_rows = 0
        for row in rows:
            if row.get("r") == "1":
                continue
            cells = row.findall("s:c", NS)
            if any(cell_value(cell, strings) not in (None, "") for cell in cells):
                data_rows += 1
            for cell in cells:
                if cell_value(cell, strings) not in (None, ""):
                    nonempty[column_number(cell.get("r"))] += 1
                if cell.get("t") == "e":
                    errors.append({"cell": cell.get("r"), "error": cell_value(cell, strings)})
        computed = [{"name": field_by_id[field_id]["fieldName"], "type": field_by_id[field_id]["type"],
                     "nonemptyValues": nonempty[index]} for index, field_id in enumerate(column_ids, 1)
                    if field_by_id[field_id]["type"] in ("formula", "filterUp", "lookup", "rollup")]
    if before != digest(path):
        raise ExportError("Downloaded workbook changed during read-only verification")
    return {"sheetName": table_name, "sheetCount": 1, "columns": len(headers), "dataRows": data_rows,
            "headerFill": True, "headerBorders": True, "computedColumns": computed,
            "sourceErrors": errors, "sha256": before, "bytesUnchanged": True}


class Exporter:
    def __init__(self, client, state_path, state):
        self.client, self.state_path, self.state = client, Path(state_path), state
        self.cleanup_attempted = False

    def save(self, **changes):
        self.state.update(changes)
        write_json(self.state_path, self.state)

    def cleanup(self):
        if self.state.get("viewDeleted"):
            return
        view = self.state.get("viewId")
        if not view:
            if self.state.get("phase") == "creating_view":
                raise ExportError("VIEW_CREATE_UNKNOWN: inspect views manually; no recorded viewId to delete")
            return
        self.cleanup_attempted = True
        existing = self.client.call("aitable", "view", "list", "--base-id", self.state["baseId"],
                                    "--table-id", self.state["tableId"])
        views = existing.get("data", {}).get("views")
        if not isinstance(views, list):
            raise ExportError("Cannot verify temporary view before deletion")
        if not any(item.get("viewId") == view for item in views):
            self.save(viewDeleted=True, cleanupRequired=False)
            return
        payload = self.client.call("aitable", "view", "delete", "--base-id", self.state["baseId"],
                                   "--table-id", self.state["tableId"], "--view-id", view, "--yes")
        if payload.get("data", {}).get("deleted") is not True:
            raise ExportError("Temporary view deletion not confirmed")
        self.save(viewDeleted=True, cleanupRequired=False)

    def proceed(self, max_polls=20):
        state = self.state
        self.cleanup_attempted = False
        if state.get("phase") == "complete":
            if digest(state["file"]) != state["verification"]["sha256"] or not state.get("viewDeleted"):
                raise ExportError("Completed artifact was changed or cleanup is incomplete")
            return self.result()
        try:
            if not state.get("viewId"):
                if state.get("phase") != "prepared":
                    raise ExportError("VIEW_CREATE_UNKNOWN: do not automatically recreate the view")
                self.save(phase="creating_view")
                payload = self.client.call("aitable", "view", "create", "--base-id", state["baseId"],
                                           "--table-id", state["tableId"], "--view-type", "Grid")
                view = payload.get("data", {})
                if not view.get("viewId"):
                    raise ExportError("VIEW_CREATE_UNKNOWN: DWS did not return viewId")
                self.save(viewId=view["viewId"], view=view, phase="view_created")
            if state["view"].get("baseId") != state["baseId"] or state["view"].get("tableId") != state["tableId"]:
                raise ExportError("Temporary view belongs to an unexpected base/table")
            check_view(state["view"], state["fields"])
            payload = {}
            if not state.get("taskId"):
                if state.get("viewDeleted"):
                    raise ExportError("Temporary view already removed; cannot submit a new export from this state")
                if state["phase"] != "view_created":
                    raise ExportError("EXPORT_SUBMIT_UNKNOWN: do not automatically resubmit")
                self.save(phase="submitting_export")
                payload = self.client.call("aitable", "export", "data", "--base-id", state["baseId"],
                                           "--scope", "view", "--table-id", state["tableId"],
                                           "--view-id", state["viewId"], "--export-format", "excel",
                                           "--timeout-ms", "1000", allow_timeout=True)
                data = payload.get("data", {})
                task_id = data.get("taskId") or payload.get("error", {}).get("details", {}).get("taskId")
                if task_id:
                    self.save(taskId=task_id, phase="polling")
                elif not data.get("downloadUrl"):
                    raise ExportError("EXPORT_SUBMIT_UNKNOWN: DWS did not return taskId or downloadUrl")
            for _ in range(max_polls):
                if payload.get("data", {}).get("downloadUrl"):
                    break
                payload = self.client.call("aitable", "export", "data", "--base-id", state["baseId"],
                                           "--task-id", state["taskId"], "--timeout-ms", "30000", allow_timeout=True)
                self.save(phase="polling", polls=state.get("polls", 0) + 1)
                if payload.get("data", {}).get("status") in ("failed", "cancelled"):
                    raise ExportError("Remote export task failed or was cancelled")
            url = payload.get("data", {}).get("downloadUrl")
            if not url:
                self.save(phase="pending")
                raise Pending("Export still running; resume this state without creating another task")
            self.save(phase="downloading")
            path = Path(state["file"])
            if not path.exists():
                download(url, path)
                self.save(downloadSha256=digest(path))
            elif not state.get("downloadSha256") or digest(path) != state["downloadSha256"]:
                raise ExportError("Existing download cannot be verified; do not overwrite it")
            self.cleanup()
            verification = verify_xlsx(path, state["tableName"], state["fields"], state["view"]["columns"])
            self.save(phase="complete", verification=verification)
            return self.result()
        except Pending:
            raise
        except Exception:
            try:
                if not self.cleanup_attempted:
                    self.cleanup()
            except Exception:
                self.save(cleanupRequired=True)
            if state.get("viewId") and not state.get("viewDeleted"):
                self.save(cleanupRequired=True)
            raise

    def result(self):
        return {"status": "complete", "file": self.state["file"], "state": str(self.state_path),
                "viewDeleted": self.state["viewDeleted"], "verification": self.state["verification"]}


def prepare(client, catalog, selection, output):
    authenticated(client, catalog["identity"])
    matches = [row for row in catalog["tables"] if selection in (row["tableId"], row["tableName"])]
    if len(matches) != 1 or "测试" in matches[0]["tableName"]:
        raise ExportError("Select exactly one non-test table from the displayed catalog")
    selected = matches[0]
    current = tables(client, catalog["baseId"])
    if selected not in current:
        raise ExportError("Table name/access changed; list tables again and ask the user to select")
    fields = field_catalog(client, catalog["baseId"], selected["tableId"])
    folder = Path(output).resolve() / (datetime.now().strftime("%Y-%m-%d_%H%M%S_") + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True, exist_ok=False)
    state = {"version": VERSION, "baseId": catalog["baseId"], **selected, "identity": catalog["identity"],
             "profile": client.profile, "fields": fields, "phase": "prepared", "viewDeleted": False,
             "file": str(folder / (file_stem(selected["tableName"]) + ".xlsx"))}
    state_path = folder / "state.json"
    write_json(state_path, state)
    return Exporter(client, state_path, state)


class StateLock:
    def __init__(self, state_path):
        self.path = Path(str(state_path) + ".lock")

    def __enter__(self):
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise ExportError("State locked; verify the owning process before removing a stale lock") from exc
        with os.fdopen(descriptor, "w") as stream:
            json.dump({"pid": os.getpid()}, stream)
        return self

    def __exit__(self, *unused):
        self.path.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--env-file", default=".env")
    listing.add_argument("--catalog", required=True)
    listing.add_argument("--profile")
    export = commands.add_parser("export")
    export.add_argument("--catalog", required=True)
    export.add_argument("--table", required=True)
    export.add_argument("--output", default="output/dingtalk_exports")
    export.add_argument("--max-polls", type=int, default=20)
    for name in ("resume", "cleanup"):
        command = commands.add_parser(name)
        command.add_argument("--state", required=True)
        command.add_argument("--max-polls", type=int, default=20)
    arguments = parser.parse_args(argv)
    exporter = None
    try:
        if hasattr(arguments, "max_polls") and not 1 <= arguments.max_polls <= 120:
            raise ExportError("max-polls must be between 1 and 120")
        if arguments.command == "list":
            result = list_catalog(Dws(arguments.profile), base_from_env(arguments.env_file), arguments.catalog)
        elif arguments.command == "export":
            catalog = read_json(arguments.catalog)
            exporter = prepare(Dws(catalog["profile"]), catalog, arguments.table, arguments.output)
            with StateLock(exporter.state_path):
                result = exporter.proceed(arguments.max_polls)
        else:
            with StateLock(arguments.state):
                state = read_json(arguments.state)
                client = Dws(state["profile"])
                authenticated(client, state["identity"])
                exporter = Exporter(client, arguments.state, state)
                if arguments.command == "cleanup":
                    exporter.cleanup()
                    result = {"status": "cleaned", "viewDeleted": exporter.state.get("viewDeleted", False)}
                else:
                    result = exporter.proceed(arguments.max_polls)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        pending = isinstance(exc, Pending)
        result = {"status": "pending" if pending else "failed",
                  "error": str(exc) if isinstance(exc, ExportError) else f"{type(exc).__name__}: inspect local state; raw details suppressed"}
        if exporter:
            result.update(state=str(exporter.state_path), viewDeleted=exporter.state.get("viewDeleted", False),
                          cleanupRequired=bool(exporter.state.get("viewId") and not exporter.state.get("viewDeleted")))
        print(json.dumps(result, ensure_ascii=False))
        return 3 if pending else 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
