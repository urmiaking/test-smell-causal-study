import csv
from pathlib import Path

from team7_pipeline import detector_batch
from team7_pipeline.detector import _classify


def test_numeric_count_and_missing_are_distinct():
    assert _classify("0") == (False, "measured")
    assert _classify("144") == (True, "measured")
    assert _classify("") == (None, "not_applicable")
    assert _classify("n/a") == (None, "not_applicable")


def test_failed_batch_is_bisected_and_logged(tmp_path: Path, monkeypatch):
    jar = tmp_path / "detector.jar"
    jar.write_bytes(b"mock-jar")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    tests = [
        {"repository_id": "r", "snapshot_sha": "sha", "test_file": f"Test{i}.java", "production_file": ""}
        for i in range(3)
    ]

    def fake_run(jar, checkout, repository_id, batch, output, timeout):
        if any(x["test_file"] == "Test1.java" for x in batch):
            raise RuntimeError("simulated legacy detector crash")
        output.mkdir(parents=True)
        with (output / "tsdetect_raw.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["App", "TestClass", "TestFilePath", "NumberOfMethods", "Sleepy Test"])
            for record in batch:
                writer.writerow(["r", record["test_file"], str(checkout / record["test_file"]), "1", "0"])
        rows = [{
            "repository_id": "r", "snapshot_sha": "sha",
            "test_file": x["test_file"], "smell_type": "Sleepy Test",
            "smell_present": False, "smell_status": "measured", "smell_raw_value": "0",
        } for x in batch]
        return rows, {
            "unmatched_output_rows": 0, "invalid_smell_values": 0, "not_applicable_smell_values": 0
        }

    monkeypatch.setattr(detector_batch, "run_single_batch", fake_run)
    rows, info = detector_batch.run_tsdetect(jar, checkout, "r", tests, tmp_path / "raw", batch_size=3)
    assert info["status"] == "partial"
    assert info["failed_test_files"] == ["Test1.java"]
    assert info["test_files_with_results"] == 2
    assert len(rows) == 2
    assert (tmp_path / "raw/tsdetect_file_failures.csv").exists()
    assert (tmp_path / "raw/tsdetect_raw.csv").exists()
