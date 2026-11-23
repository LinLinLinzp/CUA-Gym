"""Read a consistent, bounded copy of the task user's native Zotero library."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import stat
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path("/home/agent/Zotero")
FILES = ("zotero.sqlite", "zotero.sqlite-wal", "zotero.sqlite-journal")
LIMIT = 16 * 1024 * 1024
SETTLE_SECONDS = 6
RETRY_INTERVAL = 0.1


def signature(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
        raise ValueError("Invalid task library file")
    return info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def snapshot(root=ROOT):
    # Zotero can repeatedly rewrite the database and journal during startup.
    # Retry only unstable copies and bound the wait below the caller's timeout.
    deadline = time.monotonic() + SETTLE_SECONDS
    while True:
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            # The snapshot socket server uses a file-only umask; a private
            # directory must also be searchable by the unprivileged reader.
            work.chmod(0o700)
            before = [signature(root / name) for name in FILES]
            if before[0] is None:
                raise FileNotFoundError("Task library is missing")
            for name, observed in zip(FILES, before):
                if observed is None:
                    continue
                try:
                    fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                except FileNotFoundError:
                    break
                with os.fdopen(fd, "rb") as f:
                    if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                        raise ValueError("Expected a regular library file")
                    content = f.read(LIMIT + 1)
                if len(content) > LIMIT:
                    raise ValueError("Task library is oversized")
                (work / name).write_bytes(content)
            else:
                if before == [signature(root / name) for name in FILES]:
                    return consistent_database(work / FILES[0])
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Native library kept changing during snapshot")
        time.sleep(min(remaining, RETRY_INTERVAL))


def consistent_database(path):
    # Recover committed pages from the copied journal without
    # taking a lock on Zotero's running exclusive connection.
    with closing(sqlite3.connect(path)) as src, closing(sqlite3.connect(":memory:")) as dst:
        src.backup(dst)
        if dst.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("Unusable native library")
        return dst.serialize()


if __name__ == "__main__":
    sys.stdout.buffer.write(snapshot())
