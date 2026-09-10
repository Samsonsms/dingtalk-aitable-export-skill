"""Build/install only the exact source that passed offline and real DWS tests."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import zipfile

from project_checks import ROOT, SKILL_NAME, VERSION, inventory, source_digest, validate_structure


def gate(root=ROOT):
    validate_structure(root)
    expected = source_digest(root)
    offline = json.loads((root / "tmp/validation.json").read_text(encoding="utf-8"))
    live = json.loads((root / "tmp/live_smoke.json").read_text(encoding="utf-8"))
    for evidence in (offline, live):
        if evidence.get("status") != "passed" or evidence.get("sourceDigest") != expected:
            raise ValueError("Release blocked: missing, failed, or stale test evidence")
    checks = live["checks"]
    if offline.get("testCount", 0) < 1 or offline.get("failures") != 0 or offline.get("errors") != 0:
        raise ValueError("Release blocked: offline test suite did not pass")
    for key in ("headerFill", "headerBorders", "bytesUnchanged", "viewDeleted", "existingViewsUnchanged", "idempotentResume"):
        if checks.get(key) is not True:
            raise ValueError(f"Release blocked: {key}")
    if checks.get("sheetCount") != 1 or checks.get("columns", 0) < 1 or checks.get("formulaValues", 0) < 1 or checks.get("referenceValues", 0) < 1:
        raise ValueError("Release blocked: incomplete live coverage")
    artifact = Path(live["file"])
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != checks["sha256"]:
        raise ValueError("Release blocked: live artifact is missing or changed")
    return offline, live


def package_entries(root=ROOT):
    entries = {}
    for relative in inventory(root):
        if relative.startswith(("skills/", "docs/")) or relative in ("README.md", "CHANGELOG.md", ".env.example"):
            destination = relative
        else:
            continue
        entries[destination] = (root / relative).read_bytes()
    entries["install.py"] = (root / "tools/install.py").read_bytes()
    return entries


def build(root=ROOT):
    offline, live = gate(root)
    destination = root / "dist" / f"{SKILL_NAME}-{VERSION}.zip"
    if destination.exists():
        raise ValueError("Release archive exists; do not overwrite a published version")
    entries = package_entries(root)
    report = {"version": VERSION, "sourceDigest": source_digest(root), "offlineTests": offline["testCount"],
              "offlineTestedAt": offline["testedAt"], "liveTestedAt": live["testedAt"],
              "dwsVersion": live["dwsVersion"], "checks": live["checks"]}
    entries["TEST_REPORT.json"] = json.dumps(report, indent=2).encode()
    manifest = {"version": VERSION, "createdAt": datetime.now().astimezone().isoformat(),
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in entries.items()}}
    entries["MANIFEST.json"] = json.dumps(manifest, indent=2).encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            archive.writestr(name, data)
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(f"{checksum}  {destination.name}\n", encoding="utf-8")
    with zipfile.ZipFile(destination) as archive:
        for name, expected in manifest["files"].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError("Archive verification failed")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Also install the gated archive into local Codex skills")
    arguments = parser.parse_args()
    archive = build()
    result = {"archive": str(archive), "status": "released"}
    if arguments.install:
        import install
        temporary = ROOT / "tmp/release_install"
        if temporary.exists():
            raise ValueError("Install staging folder exists; inspect it before retrying")
        temporary.mkdir(parents=True)
        with zipfile.ZipFile(archive) as package:
            package.extractall(temporary)
        result["installed"] = str(install.install(temporary))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
