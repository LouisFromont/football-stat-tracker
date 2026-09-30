"""Safely extract only explicitly selected ZIP members."""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path, PurePosixPath


def safe_destination(output_directory: Path, member: str) -> Path:
    """Resolve a member below the output directory or reject it."""

    member_path = PurePosixPath(member)
    if member_path.is_absolute() or ".." in member_path.parts:
        raise ValueError(f"Unsafe ZIP member path: {member!r}")
    destination = output_directory.joinpath(*member_path.parts)
    root = output_directory.resolve()
    resolved = destination.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"ZIP member escapes output directory: {member!r}")
    return destination


def extract_selected_members(
    archive_path: Path, output_directory: Path, members: list[str]
) -> list[Path]:
    """Extract selected files, refusing missing members and overwrites."""

    if not members:
        raise ValueError("At least one member must be selected")

    with zipfile.ZipFile(archive_path) as archive:
        available = {entry.filename: entry for entry in archive.infolist()}
        missing = [member for member in members if member not in available]
        if missing:
            raise ValueError(f"Members not found in archive: {missing!r}")

        destinations = [safe_destination(output_directory, member) for member in members]
        existing = [path for path in destinations if path.exists()]
        if existing:
            raise FileExistsError(f"Refusing to overwrite existing paths: {existing!r}")

        extracted = []
        for member, destination in zip(members, destinations, strict=True):
            entry = available[member]
            if entry.is_dir():
                destination.mkdir(parents=True, exist_ok=False)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, destination.open("xb") as target:
                    shutil.copyfileobj(source, target)
            extracted.append(destination)
    return extracted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("members", nargs="*")
    parser.add_argument(
        "--manifest",
        type=Path,
        help="newline-delimited exact member names to extract",
    )
    args = parser.parse_args()

    selected = list(args.members)
    if args.manifest is not None:
        selected.extend(
            line.strip()
            for line in args.manifest.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )

    extracted = extract_selected_members(
        args.archive, args.output_directory, list(dict.fromkeys(selected))
    )
    for path in extracted:
        print(path)


if __name__ == "__main__":
    main()
