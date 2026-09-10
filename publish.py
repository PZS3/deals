#!/Library/Frameworks/Python.framework/Versions/3.9/bin/python3
"""
Commit and push deals.json so Vercel redeploys the dashboard.

Why this exists as a Python script instead of `git add && git commit && git push`
in the crontab:

The repo lives under ~/Desktop, which macOS protects with TCC. `cron` has no
Full Disk Access, so /usr/bin/git spawned straight from the crontab dies with

    fatal: Unable to read current working directory: Operation not permitted

The framework python3 does have a grant, which is why scraper.py kept working
while the push silently stopped for a week (28 Aug - 4 Sep 2026). Running git as
a CHILD of the granted interpreter should let it inherit that attribution.

If the log below still shows "Operation not permitted" after a real cron run,
the interpreter-inheritance trick did not work and the fix is one of:
  1. move this repo out of ~/Desktop (Documents and Downloads are also protected)
  2. System Settings > Privacy & Security > Full Disk Access > add /usr/sbin/cron

SECOND failure, same shape, different layer (4-10 Sep 2026): with git running,
`git add` and `git commit` both succeeded every run and only the push died with

    fatal: could not read Username for 'https://github.com': Device not configured

credential.helper was osxkeychain, and cron has no logged-in GUI session to
unlock the keychain with. Nothing upstream noticed because commit succeeded, so
deals.json stayed current locally while 18 commits piled up unpushed and the
Vercel site froze for five days. That is the signature to watch for: local data
fresh, site stale, `git rev-list --count origin/main..main` climbing.

Fixed by taking the keychain out of the path entirely — origin is now
git@github.com and auth is a passphrase-less ed25519 deploy key scoped to this
repo alone (~/.ssh/deals_deploy, installed on PZS3/deals as "deals-cron-publish"
with write access). core.sshCommand in .git/config pins that key with
IdentitiesOnly=yes. Two things this depends on, both easy to lose:
  * core.sshCommand is LOCAL repo config — a fresh clone loses it and silently
    falls back to whatever keys the agent offers.
  * github.com must be in ~/.ssh/known_hosts, or non-interactive ssh refuses to
    verify the host and the push hangs/fails instead of prompting.

To verify a change here without waiting 6h for cron, reproduce its environment:

    env -i HOME=$HOME PATH=/usr/bin:/bin git -C <repo> push origin main
"""

import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
TRACKED = ["deals.json"]

log = logging.getLogger("publish")
if not log.handlers:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] [publish] %(message)s", "%H:%M:%S"))
    log.addHandler(h)
    log.setLevel(logging.INFO)


def git(*args, check=False, quiet=False):
    """Run git as a child of this interpreter, never inheriting a shell.

    quiet=True for commands whose non-zero exit is a signal rather than a
    failure (`git diff --quiet` returns 1 to mean "there are changes").
    """
    r = subprocess.run(
        ["git", *args], cwd=str(BASE_DIR),
        capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0 and not quiet:
        msg = (r.stderr or r.stdout).strip().splitlines()
        log.error("git %s -> rc=%s: %s", " ".join(args), r.returncode, msg[0] if msg else "(no output)")
        if check:
            raise RuntimeError(f"git {' '.join(args)} failed")
    return r


def main():
    # Fail loudly and specifically if TCC is still blocking us.
    probe = git("rev-parse", "--show-toplevel", quiet=True)
    if probe.returncode != 0:
        detail = (probe.stderr or probe.stdout).strip()
        log.error("cannot run git in %s: %s", BASE_DIR, detail)
        if "Operation not permitted" in detail:
            log.error("TCC is blocking git. See the header of publish.py for the two fixes.")
        return 1

    if not git("diff", "--quiet", "--", *TRACKED, quiet=True).returncode:
        log.info("deals.json unchanged since last commit — nothing to publish")
        return 0

    git("add", "--", *TRACKED, check=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if git("commit", "-m", f"Update deals {stamp}", check=True).returncode:
        return 1

    push = git("push", "origin", "main")
    if push.returncode:
        # Say WHICH failure this is. "push failed" alone is what let the
        # keychain problem hide for five days behind a succeeding commit.
        detail = (push.stderr or push.stdout)
        if "could not read Username" in detail or "Authentication failed" in detail:
            log.error("auth failed — origin is HTTPS and no credential is reachable "
                      "from cron. See the header: origin should be git@github.com.")
        elif "Permission denied (publickey)" in detail:
            log.error("ssh key rejected — check core.sshCommand still points at "
                      "~/.ssh/deals_deploy and the deploy key is still on the repo.")
        elif "Host key verification failed" in detail:
            log.error("github.com missing from ~/.ssh/known_hosts — non-interactive "
                      "ssh cannot verify it.")
        behind = git("rev-list", "--count", "origin/main..main", quiet=True).stdout.strip()
        log.error("commit succeeded but push failed — %s commit(s) now unpushed", behind or "?")
        return 1

    log.info("published %s — Vercel will redeploy", git("rev-parse", "--short", "HEAD").stdout.strip())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:            # never let a publish failure look like success
        log.exception("publish failed: %s", e)
        sys.exit(1)
