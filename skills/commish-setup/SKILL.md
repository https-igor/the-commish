---
name: commish-setup
description: First-run onboarding for The Commish — link the owner's Sleeper fantasy football account and league, then turn on alerts. Use when `commish.py status` shows no linked account, when the owner wants to connect or switch a league, or asks to set up or change alerts.
---

# The Commish — setup

A conversation, not a form. Keep every message short.

## 1. Say hi and ask for Sleeper

One text: who you are, and ask for their **Sleeper username** (the @name in the
Sleeper app, under their profile — not their email). Mention that ESPN / Yahoo
players can still use you by telling you their roster.

## 2. Link

    /opt/hermes/.venv/bin/python3 /var/lib/hermes/skills/commish-coach/scripts/commish.py link <username>

- **One league** → it becomes the default. Confirm its name, size and scoring.
- **Several leagues** → list them by name and ask which one to focus on, then
  `commish.py use <league_id>`. They can switch any time.
- **No user / no leagues** → say what the tool said and ask them to check the
  username, or offer the manual (tell-me-your-roster) mode.

## 3. First win, right away

Immediately run `commish.py team` and `commish.py injuries`, and text the one
most useful thing: an injured or inactive starter, an empty slot, or a bench
player projected clearly higher than a starter. If the lineup is fine, say so
and name their biggest weekly edge. This is what makes them keep texting you.

## 4. Alerts

Offer the three alerts in one text and register them when they say yes:

- ⚠️ injury alerts for their roster (checked every 30 min, only texts on a change)
- 🏈 Sunday-morning lineup check (11am ET)
- 🔥 Tuesday-evening waiver targets (6pm ET)

    /opt/hermes/.venv/bin/python3 /var/lib/hermes/skills/commish-alerts/scripts/register_alerts.py

Paste its output and exit status; it is not done on a non-zero exit. To turn
one off: `hermes cron list`, then `hermes cron remove <job id>`.
