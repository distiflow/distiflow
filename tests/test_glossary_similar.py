import tomllib
import unittest

from golden import glossary, similar
from tests.helpers import REPO

GLOSSARY = tomllib.loads((REPO / "core/glossary.toml").read_text())


class Glossary(unittest.TestCase):
    def test_alias_hit_names_preferred(self):
        """S53: an alias of a glossary term is reported with the preferred word and its line; frontmatter is skipped."""
        text = '+++\nid = "x"\nnote = "pull request"\n+++\nOpen a Pull Request.\nThen a PR, or a worktree checkout.\n'
        hits = glossary.alias_hits(text, GLOSSARY)
        self.assertIn(("pull request", "change request", 5), hits)
        self.assertIn(("PR", "change request", 6), hits)
        self.assertIn(("worktree checkout", "working copy", 6), hits)
        self.assertNotIn(3, [h[2] for h in hits])
        self.assertEqual(glossary.alias_hits("a PRoblem and preprocess", GLOSSARY), [])

    def test_unknown_term_listed(self):
        """S54: back-ticked and CamelCase/ALLCAPS words outside the glossary and stoplist are listed once, sorted."""
        text = "Use `FooBar` with WidgetHub. WidgetHub again. Run git in CI with JSON. A `gate` and `TOML`. Ok No `ab`"
        self.assertEqual(glossary.unknown_terms(text, GLOSSARY), ["FooBar", "WidgetHub"])
        self.assertEqual(glossary.unknown_terms("run `golden note <id> open <text>` in `.golden/tasks/<id>/` with `--merged` and `[commands]`", GLOSSARY), [])

    def test_rewrite_lists_counts(self):
        """F1: rewriting replaces whole words, any case, and reports what changed how often."""
        out, changes = glossary.rewrite("Acme ships acme-wallet; ACME rules. Acmeish stays.",
                                        {"acme": "the project", "acme-wallet": "the service"})
        self.assertEqual(out, "the project ships the service; the project rules. Acmeish stays.")
        self.assertEqual(sorted(changes), [("acme", "the project", 2), ("acme-wallet", "the service", 1)])


CORPUS = {
    "tests-first": "Write a failing test before the fix. Run it, watch it fail for the right reason, then fix.",
    "small-steps": "Split the plan into small steps that can be checked one at a time.",
    "root-cause": "Find the root cause before changing code; never patch the symptom.",
    "review-callers": "When a shared function changes, grep every caller and check each one.",
    "evidence": "A gate passes only with recorded evidence such as command output.",
    "migrations": "Every schema migration ships with a rollback and a data check.",
    "ui-check": "Check the running app in a browser, not only the unit tests.",
}


class Similar(unittest.TestCase):
    def test_shortlist_finds_near_duplicate_top(self):
        """S55 S46: a reworded copy ranks first, clearly above the rest, and the list has k entries."""
        draft = "Before fixing, write a test that fails. Watch the test fail for the right reason, then fix it."
        top = similar.shortlist(draft, CORPUS)
        self.assertEqual(len(top), 5)
        self.assertEqual(top[0][0], "tests-first")
        self.assertGreater(top[0][1], 0.5)
        self.assertLess(top[1][1], top[0][1] / 2)
        self.assertEqual(top, sorted(top, key=lambda x: (-x[1], x[0])))

    def test_shortlist_deterministic_on_ties(self):
        """I7-style: equal scores order by id, every run."""
        corpus = {"b": "alpha beta", "a": "alpha beta", "c": "gamma"}
        runs = {tuple(similar.shortlist("alpha beta", corpus, k=3)) for _ in range(5)}
        self.assertEqual(len(runs), 1)
        self.assertEqual([x[0] for x in runs.pop()], ["a", "b", "c"])

    def test_rare_words_weigh_more(self):
        """S55: a word every practice uses counts less than a rare one (IDF)."""
        corpus = {"a": "check check check check", "b": "rollback", "c": "check one", "d": "check two"}
        self.assertEqual(similar.shortlist("check rollback", corpus, k=1)[0][0], "b")

    def test_stopwords_alone_score_zero(self):
        """S55: sharing only filler words is not similarity."""
        self.assertEqual(similar.shortlist("the and of to a", {"x": "the and of to a"}, k=1), [("x", 0.0)])

    def test_frontmatter_ignored(self):
        """S55: frontmatter keys never make two practices look alike."""
        corpus = {"x": "+++\nid = 'x'\nstages = ['plan']\n+++\ncompletely different words here"}
        [(pid, score)] = similar.shortlist("+++\nid = 'y'\nstages = ['plan']\n+++\nunrelated prose", corpus, k=1)
        self.assertEqual(score, 0.0)
