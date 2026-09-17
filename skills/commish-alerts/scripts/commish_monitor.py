# The injury-watch monitor. Installed into $HERMES_HOME/scripts/ by
# register_alerts.py because `hermes cron --monitor-script` only runs scripts
# from there. It only forwards to the root-owned copy of the tool.
import runpy
import sys

sys.argv = ["commish.py", "monitor"]
runpy.run_path("/opt/commish/commish.py", run_name="__main__")
