from pathlib import Path


def append_text(path: Path, text: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)
