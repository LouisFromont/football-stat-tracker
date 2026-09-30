"""Inspect a ZIP archive without extracting it.

The report is intentionally schema-agnostic so it can be used before the
SoccerMon archive layout has been verified from local data.
"""

from __future__ import annotations

import argparse
import json
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath


def inspect_zip(path: Path) -> dict[str, object]:
    """Return a compact, JSON-serializable ZIP inventory."""

    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()

    files = [entry for entry in entries if not entry.is_dir()]
    directories = [entry for entry in entries if entry.is_dir()]
    suffixes = Counter(
        PurePosixPath(entry.filename).suffix.lower() or "<no suffix>"
        for entry in files
    )
    top_levels = Counter(
        PurePosixPath(entry.filename).parts[0]
        for entry in entries
        if PurePosixPath(entry.filename).parts
    )
    depths = Counter(len(PurePosixPath(entry.filename).parts) for entry in entries)

    return {
        "archive": str(path),
        "archive_size_bytes": path.stat().st_size,
        "entry_count": len(entries),
        "file_count": len(files),
        "directory_count": len(directories),
        "compressed_size_bytes": sum(entry.compress_size for entry in files),
        "uncompressed_size_bytes": sum(entry.file_size for entry in files),
        "suffix_counts": dict(sorted(suffixes.items())),
        "top_level_counts": dict(sorted(top_levels.items())),
        "depth_counts": {str(key): value for key, value in sorted(depths.items())},
        "members": [entry.filename for entry in entries],
        "entries": [
            {
                "path": entry.filename,
                "size_bytes": entry.file_size,
                "compressed_size_bytes": entry.compress_size,
                "zip_modified_local": "%04d-%02d-%02dT%02d:%02d:%02d" % entry.date_time,
                "extension": PurePosixPath(entry.filename).suffix.lower(),
                "is_directory": entry.is_dir(),
                "crc32": f"{entry.CRC:08x}",
                "compression_method": entry.compress_type,
            }
            for entry in entries
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--list-members",
        action="store_true",
        help="include the complete member list in terminal output",
    )
    parser.add_argument(
        "--manifest-out",
        type=Path,
        help="write the complete member list to this text file",
    )
    args = parser.parse_args()

    report = inspect_zip(args.archive)
    members = report["members"]
    if args.manifest_out is not None:
        args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
        args.manifest_out.write_text("\n".join(members) + "\n", encoding="utf-8")
    if not args.list_members:
        report = {key: value for key, value in report.items() if key != "members"}
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
