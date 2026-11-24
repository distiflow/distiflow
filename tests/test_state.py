import json
import re
import shutil
from pathlib import Path
from unittest import mock

from distiflow import fsutil, state
from tests.helpers import REPO, DistiflowCase

FIXTURE = REPO / "tests" / "fixtures" / "state_schema1.json"
WRITER = re.compile(r"""write_text\(|write_bytes\(|open\([^)]*['"][wax]|os\.open\(""")


class State(DistiflowCase):
    def task_dir(self, data=None):
        d = self.tmp / "T-1"
        d.mkdir()
        if data is not None:
            (d / "state.json").write_text(json.dumps(data))
        return d

    def test_reads_checked_in_schema1_fixture(self):
        """T13 I11 R47: a newer distiflow reads state written by schema 1."""
        d = self.task_dir()
        shutil.copy(FIXTURE, d / "state.json")
        st = state.load(d)
        self.assertEqual(st["stage"], "plan")
        self.assertEqual([(r["stage"], r["n"]) for r in st["runs"]], [("understand", 1), ("plan", 1)])
        self.assertEqual(st["runs"][0]["evidence"]["repro-first"]["text"], "test_login fails")

    def test_missing_keys_filled_from_defaults(self):
        """T13 R47: a state missing later-added keys still loads."""
        st = state.load(self.task_dir({"schema": 1, "id": "T-1", "stage": "understand", "runs": []}))
        self.assertEqual((st["decisions"], st["open_items"], st["links"], st["status"]), ([], [], [], "active"))

    def test_newer_schema_refused_with_update_message(self):
        """T13 I11 R48: an older distiflow refuses state from a newer one, by name."""
        with self.assertRaises(state.StateError) as cm:
            state.load(self.task_dir({"schema": 2, "id": "T-9"}))
        self.assertIn("task T-9 was written by a newer distiflow (schema 2); update distiflow", str(cm.exception))

    def test_atomic_write_leaves_old_or_new(self):
        """T13 I11: a writer killed before the replace leaves the old content and no temp file."""
        target = self.tmp / "state.json"
        target.write_text("old")
        with mock.patch("distiflow.fsutil.os.replace", side_effect=OSError("killed")):
            with self.assertRaises(OSError):
                fsutil.atomic_write(target, "new")
        self.assertEqual(target.read_text(), "old")
        self.assertEqual([p.name for p in self.tmp.iterdir() if p.name != "state.json" and p.is_file()], [])
        fsutil.atomic_write(target, b"new")
        self.assertEqual(target.read_text(), "new")

    def test_save_then_load_round_trips(self):
        """T13 I11: save writes what load reads."""
        d = self.task_dir()
        st = state.new("T-1", "fix", "fix login", "0.1.0", "s-1", [{"id": "g", "evidence_wanted": "e"}])
        state.save(d, st)
        self.assertEqual(state.load(d), st)
        self.assertEqual((st["schema"], st["stage"], st["runs"][0]["stage"], st["runs"][0]["n"]),
                         (state.SCHEMA, "understand", "understand", 1))

    def test_mutate_refused_for_non_holder(self):
        """I4: only the claim holder may write task state."""
        d = self.task_dir()
        state.save(d, state.new("T-1", "fix", "x", "0.1.0", "s-1", []))
        (d / "claim").write_text(json.dumps({"session": "s-1", "nonce": "n", "since": "t"}))
        with self.assertRaises(state.StateError):
            state.mutate(d, "s-2", lambda st: st["decisions"].append({"text": "x", "at": "t"}))
        self.assertEqual(state.load(d)["decisions"], [])
        state.mutate(d, "s-1", lambda st: st["decisions"].append({"text": "x", "at": "t"}))
        self.assertEqual(len(state.load(d)["decisions"]), 1)

    def test_stale_lock_of_dead_pid_is_broken(self):
        """F5: a lock left by a crashed process does not block the task forever."""
        lock = self.tmp / "lock"
        lock.write_text("999999999")
        with fsutil.locked(lock, timeout=2):
            pass

    def test_breaking_a_dead_lock_admits_one_holder(self):
        """F5 R21 I1: two waiters on a dead lock never both get in, whichever one breaks it."""
        import os, threading, time
        lock = self.tmp / "lock"
        lock.write_text("999999999")
        real_rename, calls, inside, overlap = os.rename, [], [], []

        def slow_first_rename(*a, **kw):
            calls.append(1)
            if len(calls) == 1:
                time.sleep(0.3)  # the first breaker stalls after deciding the holder is dead
            return real_rename(*a, **kw)

        def worker(delay):
            time.sleep(delay)
            with fsutil.locked(lock, timeout=5):
                inside.append(1)
                if len(inside) > 1:
                    overlap.append(1)
                time.sleep(0.5)
                inside.pop()

        with mock.patch("os.rename", side_effect=slow_first_rename):
            ts = [threading.Thread(target=worker, args=(d,)) for d in (0, 0.1)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
        self.assertEqual(overlap, [])

    def test_single_writer_sweep(self):
        """T13 F6: fsutil.py is the only module that opens distiflow files for writing."""
        hits = []
        for f in sorted((REPO / "lib" / "distiflow").rglob("*.py")):
            if f.name == "fsutil.py":
                continue
            for n, line in enumerate(f.read_text().splitlines(), 1):
                if WRITER.search(line):
                    hits.append("%s:%d: %s" % (f.relative_to(REPO), n, line.strip()))
        self.assertEqual(hits, [], "writers outside fsutil.py:\n" + "\n".join(hits))
