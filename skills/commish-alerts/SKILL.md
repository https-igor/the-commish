---
name: commish-alerts
description: The Commish's scheduled texts — injury alerts on the owner's roster, the Sunday lineup check and the Tuesday waiver targets. Use when one of those cron jobs fires, or when the owner asks to turn alerts on, off, or re-register them.
---

# The Commish — alerts

Registered by `scripts/register_alerts.py` (create-if-missing, safe to re-run):

| job | when (UTC) | what |
| --- | --- | --- |
| `commish-injury-watch` | every 30 min | runs only when `commish.py monitor` output changes |
| `commish-sunday-lineup` | Sun 15:00 (11am ET) | lineup check before the early games |
| `commish-tuesday-waivers` | Tue 22:00 (6pm ET) | waiver targets before claims run |

Every run's final reply is texted to the owner, so **the final reply IS the
text**: short, no preamble, no mention of crons or tools.

## commish-injury-watch

You get a MONITOR CHANGE diff of `name|pos|status|starter-or-bench` lines.

- A **starter** became Out / IR / Doubtful → ⚠️ alert with the exact swap:
  run `commish.py team` and name the best eligible bench player (or a waiver
  add from `commish.py waivers --pos <POS> --limit 3` if the bench has none).
- A starter became Questionable → heads-up plus the backup plan.
- A player's designation was **removed** → one line: they are cleared.
- Bench-only changes → one line, or nothing important: reply `✅ No lineup impact.`

## commish-sunday-lineup

Run `commish.py team` and `commish.py injuries`. If something needs action
(empty slot, starter not expected to play, a clearly better bench option), text
the exact moves. Otherwise one line: `🏈 Lineup's set. Projected <total>.` plus
the opponent's projection from `commish.py matchup`.

## commish-tuesday-waivers

Run `commish.py team` and `commish.py waivers`. Text the top 1–3 targets that
fix the weakest spot, each with one reason, and a FAAB suggestion if the league
uses FAAB.

## If nothing is linked

If `commish.py status` shows no Sleeper account, the final reply is still
texted, so make it one line inviting them to send their Sleeper username.
