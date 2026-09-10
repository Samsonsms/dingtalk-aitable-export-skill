"""Behavioral tests with synthetic records and an isolated, fake DWS boundary."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("export_table", ROOT / "skills/dingtalk-aitable-export/scripts/export_table.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

FIELDS = [{"fieldId": "field_a", "fieldName": "项目", "type": "text"},
          {"fieldId": "field_b", "fieldName": "计算结果", "type": "formula"},
          {"fieldId": "field_c", "fieldName": "引用结果", "type": "filterUp"}]
TABLE = {"tableId": "table_demo", "tableName": "经营示例"}
IDENTITY = {"corp_id": "org_demo", "user_id": "user_demo"}
PROFILE = "org_demo:user_demo"
VIEW = {"viewId": "view_temporary", "baseId": "base_demo", "tableId": "table_demo", "viewType": "Grid",
        "columns": [field["fieldId"] for field in FIELDS], "filter": {"operands": [], "operator": "and"},
        "sort": [], "group": [], "custom": {}}


def xlsx_fixture(path, *, extra_sheet=False, name="经营示例", missing_column=False, fill=True, border=True,
                 error=False, cached_formula=False, empty=False, wrong_order=False, extra_data=False):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    second = '<sheet name="Unselected" sheetId="2" r:id="rId2"/>' if extra_sheet else ""
    headers = ['<c r="A1" s="1" t="inlineStr"><is><t>项目</t></is></c>',
               '<c r="B1" s="1" t="inlineStr"><is><t>计算结果</t></is></c>',
               '<c r="C1" s="1" t="inlineStr"><is><t>引用结果</t></is></c>']
    if wrong_order:
        headers[0] = headers[0].replace("项目", "引用结果")
        headers[2] = headers[2].replace("引用结果", "项目")
    if missing_column:
        headers.pop()
    numeric = '<c r="B2" t="e"><v>#DIV/0!</v></c>' if error else '<c r="B2">' + ('<f>3*2</f>' if cached_formula else '') + '<v>6</v></c>'
    data = '' if empty else '<row r="2"><c r="A2" t="inlineStr"><is><t>Demo</t></is></c>' + numeric + '<c r="C2" t="s"><v>0</v></c>' + ('<c r="D2"><v>9</v></c>' if extra_data else '') + '</row>'
    style_border = ''.join(f'<{side} style="thin"/>' if border else f'<{side}/>' for side in ('left', 'right', 'top', 'bottom'))
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{name}" sheetId="1" r:id="rId1"/>{second}</sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{ns}"><sheetData><row r="1">{"".join(headers)}</row>{data}</sheetData></worksheet>')
        archive.writestr("xl/sharedStrings.xml", f'<sst xmlns="{ns}"><si><r><t>Linked </t></r><r><t>value</t></r></si></sst>')
        archive.writestr("xl/styles.xml", f'<styleSheet xmlns="{ns}"><fills><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="{"solid" if fill else "none"}"><fgColor indexed="22"/></patternFill></fill></fills><borders><border/><border>{style_border}</border></borders><cellXfs><xf fillId="0" borderId="0"/><xf fillId="1" borderId="1"/></cellXfs></styleSheet>')


class FakeDws:
    def __init__(self):
        self.profile = PROFILE
        self.calls = []
        self.view = copy.deepcopy(VIEW)
        self.identity = dict(IDENTITY)
        self.table_rows = [dict(TABLE), {"tableId": "test_only", "tableName": "测试表"}]
        self.poll_payloads = [{"data": {"downloadUrl": "https://example.invalid/signed?secret=DO_NOT_LOG"}}]
        self.submit = {"data": {"taskId": "task_demo", "status": "pending"}}
        self.create_error = None
        self.delete_error = False
        self.profiles = [{"profile": PROFILE, "isCurrent": True, "isOrgCurrent": True}]

    def call(self, *args, **kwargs):
        self.calls.append((args, self.profile))
        if args[:2] == ("profile", "list"):
            return {"profiles": self.profiles}
        if args[:2] == ("auth", "status"):
            return {"authenticated": True, "token_valid": True, **self.identity}
        if args[:2] == ("aitable", "+list-tables"):
            return {"tables": copy.deepcopy(self.table_rows)}
        if args[:3] == ("aitable", "field", "list"):
            return {"data": {"fields": copy.deepcopy(FIELDS)}}
        if args[:3] == ("aitable", "view", "create"):
            if self.create_error:
                raise self.create_error
            return {"data": copy.deepcopy(self.view)}
        if args[:3] == ("aitable", "view", "list"):
            return {"data": {"views": [copy.deepcopy(self.view)]}}
        if args[:3] == ("aitable", "view", "delete"):
            if self.delete_error:
                raise module.ExportError("Deletion denied")
            return {"data": {"deleted": True}}
        if args[:3] == ("aitable", "export", "data"):
            if "--task-id" not in args:
                if isinstance(self.submit, Exception):
                    raise self.submit
                return self.submit
            return self.poll_payloads.pop(0) if self.poll_payloads else {"error": {"code": "TIMEOUT_ERROR"}}
        raise AssertionError(f"Unexpected call: {args}")


class ExportTests(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT / "tmp/tests"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=temporary_root)
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.client = FakeDws()
        self.catalog = {"baseId": "base_demo", "identity": dict(IDENTITY), "profile": PROFILE,
                        "tables": [dict(TABLE)]}

    def exporter(self):
        return module.prepare(self.client, self.catalog, "table_demo", self.folder / "output")

    def run_export(self, **fixture_options):
        exporter = self.exporter()
        with patch.object(module, "download", side_effect=lambda url, path: xlsx_fixture(path, **fixture_options)):
            result = exporter.proceed()
        return exporter, result

    def test_listing_waits_for_selection_without_any_write(self):
        result = module.list_catalog(self.client, "base_demo", self.folder / "catalog.json")
        self.assertEqual(result["status"], "selection_required")
        self.assertEqual(result["tables"], [TABLE])
        self.assertEqual(len(self.client.calls), 2)
        self.assertFalse(any("create" in args or "export" in args for args, _ in self.client.calls))

    def test_empty_catalog_is_not_an_export_selection(self):
        self.client.table_rows = [{"tableId": "t", "tableName": "测试"}]
        result = module.list_catalog(self.client, "base_demo", self.folder / "catalog.json")
        self.assertEqual(result["tables"], [])
        with self.assertRaises(module.ExportError):
            module.prepare(self.client, {**self.catalog, "tables": []}, "t", self.folder)

    def test_ambiguous_default_profile_requires_explicit_selection(self):
        self.client.profile = None
        self.client.profiles[0]["isOrgCurrent"] = False
        with self.assertRaises(module.ExportError):
            module.list_catalog(self.client, "base_demo", self.folder / "catalog.json")
        self.assertEqual(len(self.client.calls), 1)

    def test_default_profile_is_resolved_without_using_first_account(self):
        self.client.profile = None
        self.client.profiles.insert(0, {"profile": "unselected:user", "isCurrent": False, "isOrgCurrent": False})
        result = module.list_catalog(self.client, "base_demo", self.folder / "catalog.json")
        self.assertEqual(result["tables"], [TABLE])
        self.assertEqual(self.client.profile, PROFILE)

    def test_deletion_already_applied_is_confirmed_without_replaying_delete(self):
        exporter = self.exporter()
        exporter.save(viewId=VIEW["viewId"], view=copy.deepcopy(VIEW), phase="view_created")
        original_call = self.client.call
        def after_delete(*args, **kwargs):
            if args[:3] == ("aitable", "view", "list"):
                return {"data": {"views": []}}
            return original_call(*args, **kwargs)
        with patch.object(self.client, "call", side_effect=after_delete):
            exporter.cleanup()
        self.assertTrue(exporter.state["viewDeleted"])
        self.assertFalse(any("delete" in args for args, _ in self.client.calls))

    def test_unauthenticated_identity_cannot_list_tables(self):
        with patch.object(self.client, "call", return_value={"authenticated": False, "token_valid": False}):
            with self.assertRaisesRegex(module.ExportError, "LOGIN_REQUIRED"):
                module.list_catalog(self.client, "base_demo", self.folder / "catalog.json")

    def test_duplicate_name_is_rejected_before_mutation(self):
        self.catalog["tables"].append({"tableId": "table_other", "tableName": TABLE["tableName"]})
        with self.assertRaises(module.ExportError):
            module.prepare(self.client, self.catalog, TABLE["tableName"], self.folder)
        self.assertEqual(len(self.client.calls), 1)

    def test_table_rename_requires_reselection(self):
        self.client.table_rows[0]["tableName"] = "Changed"
        with self.assertRaises(module.ExportError):
            self.exporter()
        self.assertFalse(any("create" in args for args, _ in self.client.calls))

    def test_account_mismatch_stops_before_reading_tables(self):
        self.client.identity["user_id"] = "another_user"
        with self.assertRaises(module.ExportError):
            self.exporter()
        self.assertEqual(len(self.client.calls), 1)

    def test_full_export_is_one_view_one_task_and_unchanged_file(self):
        exporter, result = self.run_export(cached_formula=True)
        self.assertEqual(result["status"], "complete")
        self.assertTrue(result["viewDeleted"])
        self.assertEqual(result["verification"]["columns"], 3)
        self.assertEqual(result["verification"]["dataRows"], 1)
        self.assertEqual([column["nonemptyValues"] for column in result["verification"]["computedColumns"]], [1, 1])
        self.assertEqual(module.digest(result["file"]), result["verification"]["sha256"])
        requests = [args for args, _ in self.client.calls if args[:3] == ("aitable", "export", "data")]
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0][requests[0].index("--scope") + 1], "view")
        self.assertIn("table_demo", requests[0])
        self.assertIn("view_temporary", requests[0])
        self.assertNotIn("--scope", requests[1])
        self.assertEqual({profile for _, profile in self.client.calls}, {PROFILE})
        saved = exporter.state_path.read_text(encoding="utf-8")
        self.assertNotIn("DO_NOT_LOG", saved)
        self.assertNotIn("downloadUrl", saved)

    def test_timeout_resumes_same_task_and_does_not_delete_pending_view(self):
        exporter = self.exporter()
        self.client.poll_payloads = [{"error": {"code": "TIMEOUT_ERROR"}}]
        with self.assertRaises(module.Pending):
            exporter.proceed(max_polls=1)
        self.assertFalse(exporter.state["viewDeleted"])
        resumed = module.Exporter(self.client, exporter.state_path, module.read_json(exporter.state_path))
        self.client.poll_payloads = [{"data": {"downloadUrl": "https://example.invalid/file"}}]
        with patch.object(module, "download", side_effect=lambda url, path: xlsx_fixture(path)):
            resumed.proceed()
        self.assertEqual(sum(args[:3] == ("aitable", "view", "create") for args, _ in self.client.calls), 1)
        self.assertEqual(sum(args[:3] == ("aitable", "export", "data") and "--scope" in args for args, _ in self.client.calls), 1)

    def test_completed_resume_is_idempotent_without_remote_operations(self):
        exporter, original = self.run_export()
        self.client.calls.clear()
        self.assertEqual(exporter.proceed(), original)
        self.assertEqual(self.client.calls, [])

    def test_completed_file_tamper_is_detected(self):
        exporter, result = self.run_export()
        Path(result["file"]).write_bytes(b"changed")
        with self.assertRaises(module.ExportError):
            exporter.proceed()

    def test_view_with_hidden_column_or_filter_never_submits(self):
        for change in ({"columns": ["field_a"]}, {"filter": {"operands": [1]}},
                       {"custom": {"hiddenFields": {"field_b": True}}}, {"sort": [1]}):
            with self.subTest(change=change):
                self.client = FakeDws()
                self.client.view.update(change)
                exporter = self.exporter()
                with self.assertRaises(module.ExportError):
                    exporter.proceed()
                self.assertTrue(exporter.state["viewDeleted"])
                self.assertFalse(any("export" in args for args, _ in self.client.calls))

    def test_unknown_create_does_not_retry_or_delete_by_name(self):
        self.client.create_error = module.ExportError("CLI_PROCESS_TIMEOUT")
        exporter = self.exporter()
        with self.assertRaises(module.ExportError):
            exporter.proceed()
        with self.assertRaises(module.ExportError):
            exporter.proceed()
        self.assertEqual(sum("create" in args for args, _ in self.client.calls), 1)
        self.assertFalse(any("delete" in args for args, _ in self.client.calls))

    def test_unknown_submit_does_not_retry_and_cleans_recorded_view(self):
        self.client.submit = module.ExportError("CLI_PROCESS_TIMEOUT")
        exporter = self.exporter()
        for _ in range(2):
            with self.assertRaises(module.ExportError):
                exporter.proceed()
        self.assertEqual(sum("--scope" in args for args, _ in self.client.calls), 1)
        self.assertTrue(exporter.state["viewDeleted"])

    def test_download_failure_cleans_view_and_retains_task_for_resume(self):
        exporter = self.exporter()
        with patch.object(module, "download", side_effect=module.ExportError("DOWNLOAD_FAILED")):
            with self.assertRaises(module.ExportError):
                exporter.proceed()
        self.assertTrue(exporter.state["viewDeleted"])
        self.assertEqual(exporter.state["taskId"], "task_demo")

    def test_cleanup_failure_is_not_success_and_resume_does_not_redownload(self):
        self.client.delete_error = True
        exporter = self.exporter()
        with patch.object(module, "download", side_effect=lambda url, path: xlsx_fixture(path)):
            with self.assertRaises(module.ExportError):
                exporter.proceed()
        self.assertTrue(exporter.state["cleanupRequired"])
        self.client.delete_error = False
        self.client.poll_payloads = [{"data": {"downloadUrl": "https://example.invalid/file"}}]
        with patch.object(module, "download", side_effect=AssertionError("must not redownload")):
            self.assertEqual(exporter.proceed()["status"], "complete")

    def test_invalid_workbooks_fail_after_cleanup_without_repair(self):
        for options in ({"extra_sheet": True}, {"name": "Wrong"}, {"missing_column": True},
                        {"fill": False}, {"border": False}, {"wrong_order": True}, {"extra_data": True}):
            with self.subTest(options=options):
                self.client = FakeDws()
                exporter = self.exporter()
                with patch.object(module, "download", side_effect=lambda url, path: xlsx_fixture(path, **options)):
                    with self.assertRaises(module.ExportError):
                        exporter.proceed()
                self.assertTrue(exporter.state["viewDeleted"])

    def test_empty_table_is_valid_and_source_errors_are_reported_not_repaired(self):
        for options in ({"empty": True}, {"error": True}):
            self.client = FakeDws()
            _, result = self.run_export(**options)
            if options.get("empty"):
                self.assertEqual(result["verification"]["dataRows"], 0)
            else:
                self.assertEqual(result["verification"]["sourceErrors"], [{"cell": "B2", "error": "#DIV/0!"}])

    def test_repeated_selection_uses_distinct_output_folders(self):
        self.assertNotEqual(self.exporter().state_path, self.exporter().state_path)

    def test_state_lock_prevents_concurrent_resume(self):
        state = self.folder / "state.json"
        with module.StateLock(state):
            with self.assertRaises(module.ExportError):
                with module.StateLock(state):
                    pass
        self.assertFalse(Path(str(state) + ".lock").exists())

    def test_env_handles_alias_quotes_bom_and_conflicts(self):
        path = self.folder / ".env"
        for value in ('\ufeffDINGTALK_BASE_ID="base_demo" # note\nSECRET=do_not_print',
                      "baseId='base_demo'", 'DINGTALK_BASE_ID=base_demo\nbaseId=base_demo'):
            path.write_text(value, encoding="utf-8")
            self.assertEqual(module.base_from_env(path), "base_demo")
        for value in ('DINGTALK_BASE_ID=x\nbaseId=y', 'baseId=x\nbaseId=x', 'baseId=', 'baseId=YOUR_BASE_ID', 'OTHER=x'):
            path.write_text(value, encoding="utf-8")
            with self.assertRaises(module.ExportError):
                module.base_from_env(path)

    def test_download_requires_https_and_never_overwrites(self):
        with self.assertRaises(module.ExportError):
            module.download("http://example.invalid/file", self.folder / "a.xlsx")
        destination = self.folder / "a.xlsx"
        destination.write_bytes(b"original")
        with patch.object(module.shutil, "which", return_value="curl.exe"):
            with self.assertRaises(module.ExportError):
                module.download("https://example.invalid/file", destination)
        self.assertEqual(destination.read_bytes(), b"original")

    def test_curl_download_uses_argument_array_and_preserves_bytes(self):
        destination = self.folder / "a.xlsx"
        def fake_run(command, **kwargs):
            self.assertEqual(command[0], "curl.exe")
            self.assertIn("--fail", command)
            self.assertIn("-L", command)
            self.assertFalse(kwargs.get("shell", False))
            Path(command[command.index("-o") + 1]).write_bytes(b"downloaded bytes")
            return subprocess.CompletedProcess(command, 0)
        with patch.object(module.shutil, "which", return_value="curl.exe"), patch.object(module.subprocess, "run", side_effect=fake_run):
            module.download("https://example.invalid/file?x=a&b=c", destination)
        self.assertEqual(destination.read_bytes(), b"downloaded bytes")

    def test_dws_handles_timeout_json_stderr_and_redacts_raw_errors(self):
        with patch.object(module, "dws_prefix", return_value=["dws.exe"]):
            client = module.Dws(PROFILE)
        payload = {"error": {"code": "TIMEOUT_ERROR"}}
        completed = subprocess.CompletedProcess([], 1, stdout="", stderr=json.dumps(payload))
        with patch.object(module.subprocess, "run", return_value=completed):
            self.assertEqual(client.call("aitable", "export", "data", allow_timeout=True), payload)
            with self.assertRaises(module.ExportError):
                client.call("aitable", "field", "list")
        completed = subprocess.CompletedProcess([], 1, stdout="", stderr="SECRET_TOKEN_DO_NOT_PRINT")
        with patch.object(module.subprocess, "run", return_value=completed):
            with self.assertRaises(module.ExportError) as context:
                client.call("auth", "status")
            self.assertNotIn("SECRET_TOKEN", str(context.exception))

    def test_safe_filename_prevents_path_escape(self):
        for name in ('../../file', 'CON', 'file?.xlsx', '名字/表', '...'):
            safe = module.file_stem(name)
            self.assertNotIn('/', safe)
            self.assertNotIn('\\', safe)
            self.assertNotEqual(safe, '..')


if __name__ == "__main__":
    unittest.main()
