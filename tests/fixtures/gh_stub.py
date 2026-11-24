"""Stand-in for the GitHub CLI. Tests assert on the state it keeps, never on how it was called.

Env: GH_STUB_DIR (state.json lives here), GH_STUB_AUTH=ok|missing, GH_STUB_PUSH=true|false,
GH_STUB_MERGED=<branch,...>, GH_STUB_FAIL=pr-create-once.
"""
import json
import os
import sys
from pathlib import Path

STATE = Path(os.environ["GH_STUB_DIR"]) / "state.json"


def load():
    return json.loads(STATE.read_text()) if STATE.exists() else {"prs": [], "issues": [], "failed": []}


def save(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st))


def opt(args, name):
    return args[args.index(name) + 1] if name in args else None


def main(args):
    st = load()
    if args[:2] == ["auth", "status"]:
        return 0 if os.environ.get("GH_STUB_AUTH", "ok") == "ok" else 1
    if os.environ.get("GH_STUB_AUTH", "ok") != "ok":
        print("To get started with GitHub CLI, please run:  gh auth login", file=sys.stderr)
        return 4
    if args[0] == "api":
        print(os.environ.get("GH_STUB_PUSH", "true"))
        return 0
    if args[:2] == ["pr", "view"]:
        branch = args[2]
        if branch in os.environ.get("GH_STUB_MERGED", "").split(","):
            print("MERGED")
            return 0
        pr = next((p for p in st["prs"] if p["head"] == branch), None)
        if pr is None:
            print('no pull requests found for branch "%s"' % branch, file=sys.stderr)
            return 1
        print(pr["state"])
        return 0
    if args[:2] == ["pr", "list"]:
        pr = next((p for p in st["prs"] if p["head"] == opt(args, "--head")), None)
        print(pr["url"] if pr else "")
        return 0
    if args[:2] == ["pr", "create"]:
        if os.environ.get("GH_STUB_FAIL") == "pr-create-once" and "pr-create" not in st["failed"]:
            st["failed"].append("pr-create")
            save(st)
            print("pull request create failed: HTTP 502", file=sys.stderr)
            return 1
        url = "https://example.invalid/pull/%d" % (len(st["prs"]) + 1)
        st["prs"].append({"head": opt(args, "--head"), "base": opt(args, "--base"), "repo": opt(args, "--repo"),
                          "title": opt(args, "--title"), "url": url, "state": "OPEN"})
        save(st)
        print(url)
        return 0
    if args[:2] == ["issue", "create"]:
        url = "https://example.invalid/issues/%d" % (len(st["issues"]) + 1)
        body = Path(opt(args, "--body-file")).read_text() if "--body-file" in args else opt(args, "--body")
        st["issues"].append({"title": opt(args, "--title"), "repo": opt(args, "--repo"), "body": body, "url": url})
        save(st)
        print(url)
        return 0
    print("gh stub: unsupported %s" % args, file=sys.stderr)
    return 2


sys.exit(main(sys.argv[1:]))
