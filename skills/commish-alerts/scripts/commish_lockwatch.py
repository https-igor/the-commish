# The last-minute lineup monitor. Installed into $HERMES_HOME/scripts/ by
# register_alerts.py (`hermes cron --monitor-script` only runs scripts from
# there). Prints starters with a problem whose game locks within 3 hours;
# empty when there is nothing to fix, so the agent only runs on a change.
import runpy
import sys

sys.argv = ["commish.py", "lockwatch", "--hours", "3"]
runpy.run_path("/opt/commish/commish.py", run_name="__main__")
