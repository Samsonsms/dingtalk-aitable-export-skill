"""Install a verified release into Codex; refuse an existing skill directory."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

SKILL_NAME = "dingtalk-aitable-export"


def install(package, destination=None):
    package = Path(package).resolve()
    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        source = (package / relative).resolve()
        if not source.is_relative_to(package) or not source.is_file():
            raise ValueError("Invalid release manifest path")
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Release checksum mismatch: {relative}")
    if "TEST_REPORT.json" not in manifest["files"]:
        raise ValueError("Missing release test report")
    skill_prefix = "skills/" + SKILL_NAME
    source_skill = package / skill_prefix
    skill_files = {path.relative_to(package).as_posix() for path in source_skill.rglob("*") if path.is_file()}
    expected_skill_files = {path for path in manifest["files"] if path.startswith(skill_prefix + "/")}
    if not skill_files or skill_files != expected_skill_files:
        raise ValueError("Skill folder does not match release manifest")
    default_root = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "skills"
    destination = Path(destination).resolve() if destination else (default_root / SKILL_NAME).resolve()
    if destination.exists():
        raise ValueError("Skill already installed; back it up outside the skills directory before upgrading")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / (".install-" + uuid.uuid4().hex)
    shutil.copytree(source_skill, staging)
    try:
        for relative in skill_files:
            installed_file = staging / Path(relative).relative_to(skill_prefix)
            if hashlib.sha256(installed_file.read_bytes()).hexdigest() != manifest["files"][relative]:
                raise ValueError("Staged installation checksum mismatch")
        staging.rename(destination)
    except Exception:
        # Only the exact staging directory created above is removed.
        shutil.rmtree(staging)
        raise
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", help="Optional exact skill folder, not its parent")
    args = parser.parse_args()
    print(install(Path(__file__).resolve().parent, args.destination))
