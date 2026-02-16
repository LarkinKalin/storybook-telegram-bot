from pathlib import Path


def test_no_merge_conflict_markers_in_py_files() -> None:
    root = Path(__file__).resolve().parents[3]
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        if path.name == "test_no_merge_markers.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "<<<<<<< " in text or "\n=======\n" in text or ">>>>>>> " in text:
            offenders.append(str(path.relative_to(root)))
    assert not offenders, f"merge conflict markers found: {offenders}"
