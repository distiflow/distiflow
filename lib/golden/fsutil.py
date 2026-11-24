from pathlib import Path


def append_text(path: Path, text: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def create_exclusive(path: Path, text: str) -> None:
    """Create a new file; FileExistsError when it already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "x", encoding="utf-8") as f:
        f.write(text)
