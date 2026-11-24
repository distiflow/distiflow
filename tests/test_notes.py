import json

from tests.test_claim import ClaimCase


class Notes(ClaimCase):
    def g(self, *args, session="s-1"):
        return self.distiflow(*args, cwd=self.proj, root=self.root, session=session)

    def pass_gate(self, task, gate, text):
        # Gate pass lands with the gate commands; until then evidence is written the way state stores it.
        st = json.loads((task / "state.json").read_text())
        st["runs"][-1]["evidence"][gate] = {"text": text, "at": "2026-11-24T11:00:00+00:00", "session": "s-1",
                                            "carried_from": None}
        (task / "state.json").write_text(json.dumps(st))

    def test_parallel_notes_all_kept(self):
        """T12 R21: parallel notes by the holder all land."""
        task = self.start()
        rs = self.run_all([("s-1", ("note", task.name, "decision", "d%d" % i)) for i in range(20)])
        self.assertEqual([r.returncode for r in rs], [0] * 20, [r.stderr for r in rs if r.returncode])
        out = self.g("task", "show", task.name, session=None)
        self.assertEqual(out.returncode, 0, out.stderr)
        for i in range(20):
            self.assertIn("- d%d\n" % i, out.stdout)

    def test_resume_view_has_decisions_open_items_last_gate(self):
        """S32: a new session resumes with every decision, the open items still open and the last passed gate."""
        task = self.start()
        for args in (("decision", "keep", "the", "old", "api"), ("decision", "no", "migration"),
                     ("open", "check", "mobile"), ("open", "ask", "design"), ("close", "1")):
            r = self.g("note", task.name, *args)
            self.assertEqual(r.returncode, 0, r.stderr)
        self.pass_gate(task, "g", "repro: test_login fails\nmore lines")
        (task / "claim").unlink()
        r = self.g("task", "resume", task.name, session="s-2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("decisions: keep the old api · no migration", r.stdout)
        self.assertIn("open items: #2 ask design\n", r.stdout)
        self.assertNotIn("check mobile", r.stdout)
        self.assertIn("last passed gate: g (repro: test_login fails)", r.stdout)
        self.assertIn("pending gates: none", r.stdout)
        self.assertIn("brief: .distiflow/tasks/%s/stage-1-brief.md" % task.name, r.stdout)

    def test_interrupted_and_no_unearned_pass(self):
        """S37: a stage left open by another session shows interrupted, and no gate passes unearned."""
        task = self.start("s-1")
        (task / "claim").unlink()
        r = self.g("task", "resume", task.name, session="s-2")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("stage 1/6 understand (interrupted)", r.stdout)
        self.assertIn("last passed gate: none", r.stdout)
        self.assertIn("pending gates: g", r.stdout)
        r = self.g("task", "resume", task.name, session="s-2")
        self.assertIn("stage 1/6 understand (interrupted)", r.stdout)
        own = self.start("s-3")
        r = self.g("task", "resume", own.name, session="s-3")
        self.assertIn("stage 1/6 understand (active)", r.stdout)

    def test_missing_snapshot_regenerated(self):
        """R55: a missing brief snapshot is rebuilt on resume, not a crash."""
        task = self.start()
        (task / "stage-1-brief.md").unlink()
        r = self.g("task", "resume", task.name)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("brief snapshot missing; regenerated", r.stdout)
        self.assertTrue((task / "stage-1-brief.md").read_text().startswith("# %s · feature" % task.name))

    def test_non_holder_note_refused(self):
        """I4: a session that does not hold the task cannot write its state."""
        task = self.start("s-1")
        before = (task / "state.json").read_bytes()
        for args in (("decision", "x"), ("open", "y"), ("close", "1")):
            with self.subTest(args=args):
                r = self.g("note", task.name, *args, session="s-2")
                self.assertEqual(r.returncode, 1)
                self.assertIn("you do not hold task %s" % task.name, r.stderr)
        self.assertEqual((task / "state.json").read_bytes(), before)
        r = self.g("note", task.name, "close", "7")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no open item 7", r.stderr)
