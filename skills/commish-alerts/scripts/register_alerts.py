#!/opt/hermes/.venv/bin/python3
"""Register The Commish's three alert jobs with `hermes cron`. Create-if-missing.

Run as the gateway's own user (from a chat turn), never via a root `docker exec`:
a root-created jobs.json cannot be managed by the gateway afterwards.
"""
import json
import os
import shutil
import subprocess
import sys

HERMES_HOME = os.environ.get("HERMES_HOME", "/var/lib/hermes")
HERMES = shutil.which("hermes") or "/opt/hermes/.venv/bin/hermes"
JOBS_FILE = os.path.join(HERMES_HOME, "cron", "jobs.json")
HERE = os.path.dirname(os.path.abspath(__file__))

JOBS = [
    {
        "name": "commish-injury-watch",
        "schedule": "*/30 * * * *",
        "monitor": "commish_monitor.py",
        "prompt": "Injury watch for the owner's fantasy roster: the injury designations changed. "
                  "Follow the commish-alerts skill (commish-injury-watch) and reply with the text for the owner.",
    },
    {
        "name": "commish-sunday-lineup",
        "schedule": "0 15 * * 0",
        "prompt": "Sunday lineup check before the early NFL games. Follow the commish-alerts skill "
                  "(commish-sunday-lineup) and reply with the text for the owner.",
    },
    {
        "name": "commish-tuesday-waivers",
        "schedule": "0 22 * * 2",
        "prompt": "Tuesday waiver targets. Follow the commish-alerts skill (commish-tuesday-waivers) "
                  "and reply with the text for the owner.",
    },
]


def existing_names():
    try:
        with open(JOBS_FILE) as f:
            data = json.load(f)
    except FileNotFoundError:
        return set()
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    return {j.get("name") for j in jobs}


def main():
    channel = (os.environ.get("PLOW_HOME_CHANNEL") or "").strip()
    if not channel:
        print("refusing: PLOW_HOME_CHANNEL is not set, so alerts would have nowhere to go")
        return 1
    scripts = os.path.join(HERMES_HOME, "scripts")
    os.makedirs(scripts, exist_ok=True)
    shutil.copyfile(os.path.join(HERE, "commish_monitor.py"), os.path.join(scripts, "commish_monitor.py"))

    have = existing_names()
    failed = 0
    for job in JOBS:
        if job["name"] in have:
            print(f"already registered: {job['name']}")
            continue
        argv = [HERMES, "cron", "create", job["schedule"], job["prompt"], "--name", job["name"],
                "--skill", "commish-alerts", "--skill", "commish-coach",
                "--deliver", f"plow_chat:{channel}"]
        if job.get("monitor"):
            argv += ["--monitor-script", job["monitor"]]
        proc = subprocess.run(argv, capture_output=True, text=True)
        if proc.returncode == 0:
            print(f"registered: {job['name']} ({job['schedule']} UTC)")
        else:
            failed += 1
            print(f"FAILED: {job['name']}: {(proc.stderr or proc.stdout).strip()}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
