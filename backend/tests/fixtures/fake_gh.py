"""A stand-in for the GitHub CLI used by the kit tests.

``repo create`` makes a bare repository under ``FAKE_GH_REMOTES`` and pushes to it with real git, so a test can check
what was pushed without the network. ``FAKE_GH_SIGNED_OUT`` fails ``auth status``; every call is appended to
``FAKE_GH_RECORD`` as one JSON line.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

args = sys.argv[1:]
record = os.environ.get("FAKE_GH_RECORD")
if record:
    with open(record, "a", encoding="utf-8") as f:
        f.write(json.dumps(args) + "\n")

if args[:1] == ["--version"]:
    print("gh version 2.99.0 (fake)")
    sys.exit(0)
if args[:2] == ["auth", "status"]:
    sys.exit(1 if os.environ.get("FAKE_GH_SIGNED_OUT") else 0)
if args[:2] == ["api", "user"]:
    print("kit-tester")
    sys.exit(0)
if args[:2] == ["repo", "create"]:
    name = args[2]
    source = Path(args[args.index("--source") + 1])
    remote = Path(os.environ["FAKE_GH_REMOTES"]) / f"{name}.git"
    if remote.exists():
        print("GraphQL: Name already exists on this account (createRepository)", file=sys.stderr)
        sys.exit(1)
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    subprocess.run(["git", "-C", str(source), "remote", "add", "origin", str(remote)], check=True)
    subprocess.run(["git", "-C", str(source), "push", "-q", "-u", "origin", "main"], check=True)
    print(f"https://github.com/kit-tester/{name}")
    sys.exit(0)
print(f"fake gh: unknown command {args}", file=sys.stderr)
sys.exit(2)
