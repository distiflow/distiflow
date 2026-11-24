import contextlib
import os
import secrets
import time
from pathlib import Path


def append_text(path: Path, text: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def _write_temp(path: Path, data: str | bytes) -> Path:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    tmp = path.with_name(".%s.%d.%s.tmp" % (path.name, os.getpid(), secrets.token_hex(4)))
    try:
        with open(tmp, "wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def create_exclusive(path: Path, text: str) -> None:
    """Create a new file with its full content in one step; FileExistsError when it already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _write_temp(path, text)
    try:
        os.link(tmp, path)  # a reader never sees the file empty
    finally:
        tmp.unlink(missing_ok=True)


def atomic_write(path: Path, data: str | bytes) -> None:
    """Readers see the old file or the new one, never a partial write."""
    tmp = _write_temp(path, data)
    try:
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@contextlib.contextmanager
def locked(path: Path, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while True:
        try:
            create_exclusive(path, str(os.getpid()))
            break
        except FileExistsError:
            try:
                pid = int(path.read_text() or "0")
            except (FileNotFoundError, ValueError):
                pid = None
            # A lock whose writer died is moved aside under a unique name, so two breakers cannot both win.
            if pid is not None and not _alive(pid):
                with contextlib.suppress(FileNotFoundError):
                    os.rename(path, path.with_name("%s.dead.%d.%d" % (path.name, pid, os.getpid())))
                continue
            if time.monotonic() > deadline:
                raise TimeoutError("lock %s held by pid %s" % (path, pid))
            time.sleep(0.01)
    try:
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
