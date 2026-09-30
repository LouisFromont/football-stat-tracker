from __future__ import annotations

import importlib.util
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import ModuleType


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str) -> ModuleType:
    path = REPOSITORY_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inspect_zip_archive = load_script("inspect_zip_archive")
extract_zip_members = load_script("extract_zip_members")
inspect_parquet = load_script("inspect_parquet")


class FakeColumn:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def to_pylist(self) -> list[object]:
        return self.values


class ZipInspectionToolTests(unittest.TestCase):
    def test_inventory_reports_structure_without_extracting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "sample.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("year/month/day.zip", b"nested")
                archive.writestr("year/readme.txt", "metadata")

            report = inspect_zip_archive.inspect_zip(archive_path)

            self.assertEqual(report["file_count"], 2)
            self.assertEqual(report["suffix_counts"], {".txt": 1, ".zip": 1})
            self.assertEqual(report["top_level_counts"], {"year": 2})
            self.assertFalse((root / "year").exists())

    def test_selected_extraction_preserves_paths_and_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "sample.zip"
            output = root / "raw"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("month/day.zip", b"selected")
                archive.writestr("month/other.zip", b"not selected")

            extracted = extract_zip_members.extract_selected_members(
                archive_path, output, ["month/day.zip"]
            )

            self.assertEqual(extracted, [output / "month/day.zip"])
            self.assertEqual(extracted[0].read_bytes(), b"selected")
            self.assertFalse((output / "month/other.zip").exists())

    def test_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "unsafe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../escape.txt", "unsafe")

            with self.assertRaises(ValueError):
                extract_zip_members.extract_selected_members(
                    archive_path, root / "output", ["../escape.txt"]
                )
            self.assertFalse((root / "escape.txt").exists())

    def test_existing_file_is_not_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "sample.zip"
            output = root / "raw"
            existing = output / "day.zip"
            existing.parent.mkdir()
            existing.write_bytes(b"keep")
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("day.zip", b"replace")

            with self.assertRaises(FileExistsError):
                extract_zip_members.extract_selected_members(
                    archive_path, output, ["day.zip"]
                )
            self.assertEqual(existing.read_bytes(), b"keep")


class ParquetInspectionHelperTests(unittest.TestCase):
    def test_millisecond_time_strings_produce_cadence(self) -> None:
        profile = inspect_parquet._cadence_profile(
            FakeColumn(["10:00:00.000", "10:00:00.010", "10:00:00.020"]),
            "seconds",
        )
        self.assertAlmostEqual(profile["median_positive_delta_s"], 0.01)
        self.assertAlmostEqual(profile["estimated_frequency_hz"], 100.0)

    def test_cadence_reports_duplicate_and_negative_deltas(self) -> None:
        profile = inspect_parquet._cadence_profile(
            FakeColumn([1000.0, 1000.0, 999.0, 1010.0]), "milliseconds"
        )
        self.assertEqual(profile["duplicate_delta_count"], 1)
        self.assertEqual(profile["negative_delta_count"], 1)


if __name__ == "__main__":
    unittest.main()
