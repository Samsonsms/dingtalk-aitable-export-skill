"""Run offline tests and record evidence tied to the current source tree."""

from datetime import datetime
import json
import sys
import unittest

from project_checks import ROOT, source_digest, validate_structure


def main():
    structure = validate_structure()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    evidence = {"status": "passed" if result.wasSuccessful() and result.testsRun else "failed",
                "testCount": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                "structure": structure, "sourceDigest": source_digest(),
                "testedAt": datetime.now().astimezone().isoformat(), "python": sys.version.split()[0]}
    path = ROOT / "tmp/validation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence))
    return 0 if evidence["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
