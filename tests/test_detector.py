import csv
from pathlib import Path

from team7_pipeline.detector import parse_tsdetect


def test_tsdetect_v22_numeric_flags_and_real_file_path(tmp_path: Path):
    checkout = tmp_path / "checkout"
    test = checkout / "src/test/java/SampleTest.java"
    test.parent.mkdir(parents=True)
    test.write_text("class SampleTest {}", encoding="utf-8")
    out = tmp_path / "raw.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["App", "TestClass", "TestFilePath", "ProductionFilePath", "NumberOfMethods", "Assertion Roulette", "Sleepy Test"])
        writer.writerow(["sample", "SampleTest.java", str(test), "", "1", "1", "0"])
        writer.writerow(["sample", "Other.java", str(checkout / "Other.java"), "", "1", "0", "1"])
    smells, stats = parse_tsdetect(
        out, [{"repository_id": "r", "snapshot_sha": "s", "test_file": "src/test/java/SampleTest.java"}], checkout
    )
    assert [(r["smell_type"], r["smell_present"]) for r in smells] == [
        ("Assertion Roulette", True), ("Sleepy Test", False)
    ]
    assert stats["matched_test_files"] == 1
    assert stats["unmatched_output_rows"] == 1


def test_legacy_true_false_schema(tmp_path: Path):
    checkout = tmp_path / "source"
    test = checkout / "test/XTest.java"
    test.parent.mkdir(parents=True)
    test.write_text("class XTest {}", encoding="utf-8")
    raw = tmp_path / "raw.csv"
    raw.write_text("App,TestClass,ProductionClass,Assertion Roulette,Sleepy Test\nr," + str(test) + ",,true,false\n", encoding="utf-8")
    smells, stats = parse_tsdetect(
        raw, [{"repository_id": "r", "snapshot_sha": "s", "test_file": "test/XTest.java"}], checkout
    )
    assert len(smells) == 2 and stats["unmatched_output_rows"] == 0
