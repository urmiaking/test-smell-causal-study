import csv
from pathlib import Path

from team7_pipeline.detector import parse_tsdetect


def test_tsdetect_true_false_and_unmatched(tmp_path: Path):
    checkout = tmp_path / "checkout"
    test = checkout / "src/test/java/SampleTest.java"
    test.parent.mkdir(parents=True)
    test.write_text("class SampleTest {}", encoding="utf-8")
    out = tmp_path / "raw.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["App", "TestClass", "ProductionClass", "Assertion Roulette", "Sleepy Test"])
        writer.writerow(["sample", str(test), "", "true", "false"])
        writer.writerow(["sample", str(checkout / "Other.java"), "", "true", "true"])
    smells, stats = parse_tsdetect(out, [{"repository_id": "r", "snapshot_sha": "s", "test_file": "src/test/java/SampleTest.java"}], checkout)
    assert [(r["smell_type"], r["smell_present"]) for r in smells] == [
        ("Assertion Roulette", True), ("Sleepy Test", False)
    ]
    assert stats["matched_test_files"] == 1
    assert stats["unmatched_output_rows"] == 1
