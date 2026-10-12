import json
import subprocess
import sys
import time

PR_NUMBER = "490"

def all_completed():
    result = subprocess.run(
        ["gh", "pr", "view", PR_NUMBER, "--json", "statusCheckRollup"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("gh command failed", file=sys.stderr)
        sys.exit(1)
    data = json.loads(result.stdout)
    rolls = data.get("statusCheckRollup", [])
    return all(item.get("status") == "COMPLETED" for item in rolls)

while True:
    if all_completed():
        print(f"All PR #{PR_NUMBER} CI checks completed")
        break
    time.sleep(30)
