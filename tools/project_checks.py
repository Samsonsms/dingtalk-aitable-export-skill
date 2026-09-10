"""Shared source inventory and validation for the release gate (stdlib only)."""

import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "dingtalk-aitable-export"
SKILL = ROOT / "skills" / SKILL_NAME
VERSION = "1.0.0"
DIRECTORIES = ("skills", "tools", "tests", "docs")
ROOT_FILES = ("README.md", "AGENTS.md", "CHANGELOG.md", ".env.example", ".gitignore")


def inventory(root=ROOT):
    files = [root / name for name in ROOT_FILES if (root / name).is_file()]
    for directory in DIRECTORIES:
        files.extend(path for path in (root / directory).rglob("*")
                     if path.is_file() and "__pycache__" not in path.parts and path.suffix in (".py", ".md", ".yaml"))
    return {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(files)}


def source_digest(root=ROOT):
    return hashlib.sha256(json.dumps(inventory(root), sort_keys=True).encode()).hexdigest()


def validate_structure(root=ROOT):
    skill = root / "skills" / SKILL_NAME
    entry = (skill / "SKILL.md").read_text(encoding="utf-8")
    if not entry.startswith("---\n"):
        raise ValueError("Missing skill frontmatter")
    frontmatter = entry.split("---", 2)[1]
    if not re.search(rf"^name: {SKILL_NAME}$", frontmatter, re.M) or not re.search(r"^description: .+", frontmatter, re.M):
        raise ValueError("Invalid skill name/description")
    if not (skill / "agents/openai.yaml").is_file():
        raise ValueError("Missing UI metadata")
    for relative in inventory(root):
        path = root / relative
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".py":
            ast.parse(text, filename=relative)
        if path.suffix == ".md":
            for target in re.findall(r"\]\(([^)]+)\)", text):
                if "://" in target or target.startswith("#"):
                    continue
                target_path = target.split("#", 1)[0]
                if "<" not in target_path and not (path.parent / target_path).exists():
                    raise ValueError(f"Broken Markdown link: {relative}: {target}")
    if VERSION not in (skill / "scripts/export_table.py").read_text(encoding="utf-8"):
        raise ValueError("Version mismatch")
    return {"frontmatter": True, "pythonSyntax": True, "localLinks": True}
