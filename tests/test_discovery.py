from pathlib import Path

from team7_pipeline.discovery import discover, is_test_file


def test_detect_and_match_production(tmp_path: Path):
    test = tmp_path / "app/src/test/java/com/acme/ThingTest.java"
    prod = tmp_path / "app/src/main/java/com/acme/Thing.java"
    test.parent.mkdir(parents=True)
    prod.parent.mkdir(parents=True)
    test.write_text("class ThingTest { void x() { assertEquals(1, 1); } }", encoding="utf-8")
    prod.write_text("class Thing {}", encoding="utf-8")
    rows = discover(tmp_path, "a", "abc")
    assert len(rows) == 1
    assert rows[0]["production_file"] == "app/src/main/java/com/acme/Thing.java"
    assert rows[0]["assert_count"] == 1


def test_no_source_is_not_fabricated(tmp_path: Path):
    test = tmp_path / "src/test/java/FooTest.java"
    test.parent.mkdir(parents=True)
    test.write_text("class FooTest {}", encoding="utf-8")
    assert discover(tmp_path, "r", "sha")[0]["production_file"] == ""
    assert is_test_file("src/test/java/FooTest.java")
    assert not is_test_file("src/main/java/Foo.java")
