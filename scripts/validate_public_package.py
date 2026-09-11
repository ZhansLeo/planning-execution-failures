from __future__ import annotations

import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def walk_metrics(value, path="root"):
    if isinstance(value, dict):
        required = {"value", "unit", "numerator", "denominator"}
        if required.issubset(value):
            denominator = value["denominator"]
            if denominator == 0:
                raise AssertionError(f"zero denominator at {path}")
            if value["unit"] == "rate" or "/query" in value["unit"]:
                expected = value["numerator"] / denominator
                if not math.isclose(float(value["value"]), float(expected), rel_tol=1e-8, abs_tol=1e-8):
                    raise AssertionError(f"ratio mismatch at {path}")
        for key, child in value.items():
            walk_metrics(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk_metrics(child, f"{path}[{index}]")


def main() -> None:
    master = json.loads((ROOT / "research" / "results_master.json").read_text(encoding="utf-8"))
    taxonomy = json.loads((ROOT / "research" / "unified_failure_taxonomy.json").read_text(encoding="utf-8"))
    literature = json.loads((ROOT / "research" / "literature_evidence.json").read_text(encoding="utf-8"))
    bib = (ROOT / "references" / "references.bib").read_text(encoding="utf-8")

    walk_metrics(master)
    if len(taxonomy["layers"]) != 8:
        raise AssertionError("failure taxonomy must contain eight layers")

    bib_keys = set(re.findall(r"@[A-Za-z]+\{([^,]+),", bib))
    missing = {item["cite_key"] for item in literature["sources"]} - bib_keys
    if missing:
        raise AssertionError(f"missing BibTeX keys: {sorted(missing)}")

    required = [
        ROOT / "README.md",
        ROOT / "research" / "research_narrative.md",
        ROOT / "research" / "results_master.json",
        ROOT / "deck" / "Diagnosing_Planning_Execution_Failures.pptx",
    ]
    if missing_files := [str(path.relative_to(ROOT)) for path in required if not path.exists()]:
        raise AssertionError(f"missing release files: {missing_files}")

    secret_patterns = [
        re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
        re.compile(r"(?i)(api[_-]?key|secret)\s*[=:]\s*['\"]?[A-Za-z0-9_-]{16,}"),
        re.compile(r"(?i)[A-Z]:[/\\]Users[/\\]"),
    ]
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".md", ".json", ".py", ".bib"}:
            text = path.read_text(encoding="utf-8")
            if any(pattern.search(text) for pattern in secret_patterns):
                raise AssertionError(f"sensitive or local-path content in {path.relative_to(ROOT)}")

    print(json.dumps({"status": "passed", "metric_source": "results_master.json", "taxonomy_layers": 8}, indent=2))


if __name__ == "__main__":
    main()
