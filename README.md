# The Commish 🏈

A fantasy football expert that lives in your texts. Built on
[Plow](https://github.com/plow-pbc/plow-agents) and the
[plow-hermes-agent](https://github.com/plow-pbc/plow-hermes-agent) base image.

Text it like a friend who knows the injury report before kickoff:

> **You:** Diggs or Metcalf this week?
> **The Commish:** Metcalf in. 🏈
> 10.2 vs 9.9, coin flip. Diggs draws the TOUGH matchup (DAL).

- **Start/sit** calls from weekly projections, matchup and injury status
- **Lineup check** for your Sleeper league (empty slots, injured starters, better bench options)
- **Waiver targets** that fix your weakest spot, with FAAB suggestions
- **Trade verdicts**: Accept / Decline / Counter
- **Last-minute reminders**: a starter is out / questionable / on bye and his game locks within 3 hours, with the exact swap
- **Matchups & news**: defense-vs-position ranks from this season's stats, latest ESPN fantasy news
- **Alerts**: injury changes on your roster, Sunday-morning lineup check, Tuesday waiver targets
- **Short answers**: texts, not essays, and every reason comes from the data

Data: [Sleeper API](https://docs.sleeper.com/) (league, rosters, projections, trending adds) and the
ESPN injury report. No API keys. ESPN/Yahoo leagues work in manual mode (tell it your players).

## Layout

```
runtime/persona.md          who The Commish is
skills/commish-coach/       the brain + scripts/commish.py (all data access)
skills/commish-setup/       onboarding: link Sleeper, first win, alerts
skills/commish-alerts/      scheduled texts + register_alerts.py
image/s6-overlay/           Agent Index usage reporter (s6 longrun)
vendor/client.pin           pinned Agent Index client
```

## Run locally

```sh
export PATH="/path/to/plow-agents/bin:$PATH"
plow-agents login            # text the activation code from your phone
plow-agents lines
plow-agents mint ln_xxx      # writes ./plow-credentials (git- and docker-ignored)
docker compose up --build -d
```

Try the tool on its own (no Plow needed):

```sh
COMMISH_HOME=.commish-test python3 skills/commish-coach/scripts/commish.py link <sleeper_username>
COMMISH_HOME=.commish-test python3 skills/commish-coach/scripts/commish.py team
```

Usage is reported to the [Agent Index](https://aiworthusing.com/agent-index/the-commish)
as `AGENT_ID=the-commish` (daily token counts per model, nothing else).

## License

MIT
