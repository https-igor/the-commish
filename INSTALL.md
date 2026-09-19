# Install The Commish 🏈

Text your own fantasy football expert. About 15 minutes, no API keys — the NFL
data (Sleeper, ESPN) is public and free.

**What you need:** Docker, Python 3.11+, git, and a phone that can send a text.
A Sleeper league helps; ESPN/Yahoo players can still use it in manual mode.

## 1. Get a Plow line

Plow is the chat platform the agent answers on. The phone number comes from a
shared pool, so grab one while it is free.

```sh
git clone https://github.com/plow-pbc/plow-agents.git
export PATH="$PWD/plow-agents/bin:$PATH"
plow-agents login          # text the code it prints, from the phone you will text the agent with
plow-agents lines          # pick a line whose STATUS is 'free'
```

## 2. Run the agent

```sh
git clone https://github.com/https-igor/the-commish.git
cd the-commish
plow-agents mint ln_xxx    # the free line from step 1; writes ./plow-credentials
docker compose up --build -d
```

The first boot waits for your first text. Send anything ("hey") to the number
`plow-agents lines` shows for that line. If it stays quiet for a minute, run
`docker compose restart` — the container adopts the chat on boot.

## 3. Link your league

The Commish asks for your **Sleeper username** (the @name in the Sleeper app,
under your profile — not your email). It finds your leagues, and if you are in
several it asks which one. Then it reads your roster and texts you the first
thing worth fixing.

Say yes when it offers alerts, and it registers these scheduled texts:

| Alert | When |
| --- | --- |
| ⏰ last-minute lineup fix | a starter is Out/Questionable/on bye and his game kicks off within 3h |
| ⚠️ injury change on your roster | checked every 30 min, texts only when a designation changes |
| 📊 weekly recap | Tuesday 9am ET, after Monday night football |
| 🔥 waiver targets | Tuesday 6pm ET, before claims process |
| 🏈 lineup check | Sunday 11am ET |

New to fantasy? Tell it so ("I've never played") and it explains every term as
it comes up, in three or four words, without turning into a lecture.

## What to text it

```
who should I start at flex?          anything I need to fix?
Diggs or Metcalf?                    who should I pick up this week?
is this trade fair: my Gibbs for his Bijan + Bigsby?
any news on Ja'Marr Chase?           which defenses are worst against WRs?
how did I do last week?              where am I in the standings?
what did everyone pick up?
```

## Keeping it running

| To | Run |
| --- | --- |
| rebuild after pulling changes | `git pull && docker compose up --build -d` |
| see what it is doing | `docker compose logs -f` |
| stop, keep its memory | `docker compose stop` |
| stop and release the line | `plow-agents revoke && docker compose down -v` |

`docker compose down -v` deletes the agent's memory and your linked league.
Releasing the line gives the number back to the pool, and someone else may
take it.

## ESPN / Yahoo leagues

Those platforms have no public API, so The Commish cannot read that roster.
Tell it your players and it still gives start/sit, waiver and trade calls from
the same projections, matchup ranks and injury data (it assumes PPR scoring
unless you say otherwise).

## Privacy

The agent runs on your machine. It holds your Plow credential and your linked
Sleeper **username** (public data) — nothing else about you. Usage reporting
sends daily token counts per model to the [Agent
Index](https://aiworthusing.com/agent-index/the-commish) and nothing else: no
messages, no roster, no league. The reporter is the Plow base image's own;
set `AGENT_ID` empty in compose.yml to leave it out.
