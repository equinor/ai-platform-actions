"""Pin a Docker action definition to a published image digest."""

from __future__ import annotations

import re
import sys
from pathlib import Path

SOURCE_BUILD_IMAGE = "Dockerfile"
DIGEST_REFERENCE = re.compile(r"^ghcr\.io/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$")


def find_runs_image_line(lines: list[str]) -> int:
    inside_runs = False
    for index, line in enumerate(lines):
        if line.startswith("runs:"):
            inside_runs = True
            continue
        if inside_runs and line.strip() and not line[:1].isspace():
            inside_runs = False
        if inside_runs and line.strip().startswith("image:"):
            return index
    raise ValueError("action definition has no runs.image entry")


def pin(text: str, reference: str) -> str:
    lines = text.splitlines(keepends=True)
    index = find_runs_image_line(lines)
    line = lines[index]
    current = line.split(":", 1)[1].strip()
    if current != SOURCE_BUILD_IMAGE:
        raise ValueError(f"runs.image is already {current!r}, expected {SOURCE_BUILD_IMAGE!r}")
    stripped = line.rstrip("\r\n")
    indent = stripped[: len(stripped) - len(stripped.lstrip())]
    lines[index] = f"{indent}image: docker://{reference}{line[len(stripped):]}"
    return "".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("❌ Usage: pin_action_image.py <action.yaml> <ghcr-reference@sha256:...>")
        return 2

    action_path = Path(argv[1])
    reference = argv[2]

    if not DIGEST_REFERENCE.match(reference):
        print(f"❌ Not a digest-pinned GHCR reference: {reference}")
        return 1
    if not action_path.is_file():
        print(f"❌ Action definition not found: {action_path}")
        return 1

    try:
        pinned = pin(action_path.read_text(encoding="utf-8", newline=""), reference)
    except ValueError as error:
        print(f"❌ {action_path}: {error}")
        return 1

    action_path.write_text(pinned, encoding="utf-8", newline="")
    print(f"✅ {action_path} pinned to docker://{reference}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
