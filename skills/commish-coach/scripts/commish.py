#!/usr/bin/env python3
"""The Commish: fantasy football data for the agent. Standard library only.

Every subcommand prints plain text the agent reads and turns into advice.
Data comes from public, keyless feeds:
  - Sleeper API (api.sleeper.app): NFL state, users, leagues, rosters, matchups,
    players, trending adds.
  - Sleeper projections (api.sleeper.com/projections): weekly and season points.
  - ESPN (site.api.espn.com): injury report comments.

State lives in $COMMISH_HOME (default /var/lib/hermes/commish): the owner's
linked Sleeper account and caches. Nothing here writes outside it.

    commish.py link <sleeper_username>      link the owner's Sleeper account
    commish.py use <league_id>              pick the default league
    commish.py status                       what is linked, current NFL week
    commish.py team                         my roster, projections, injuries
    commish.py matchup                      this week's opponent, projected totals
    commish.py startsit "<name>" "<name>"   compare players for this week
    commish.py waivers [--pos RB] [--limit 10]
    commish.py trade --give "A, B" --get "C, D"
    commish.py player "<name>"              one player's card
    commish.py injuries                     injured/questionable players on my roster
    commish.py monitor                      stable snapshot for the alert cron
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

HOME = os.environ.get("COMMISH_HOME", "/var/lib/hermes/commish")
CONFIG = os.path.join(HOME, "config.json")
SLEEPER = "https://api.sleeper.app/v1"
PROJ = "https://api.sleeper.com/projections/nfl"
ESPN_INJURIES = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
UA = "the-commish/1.0 (+https://aiworthusing.com/agent-index)"


def die(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(1)


# --- http + cache ------------------------------------------------------------


def fetch(url: str, timeout: int = 30):
    # ESPN refuses unfamiliar User-Agents (403), so it gets urllib's default.
    headers = {"Accept": "application/json"}
    if "espn.com" not in url:
        headers["User-Agent"] = UA
    req = urllib.request.Request(url, headers=headers)
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            last = e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
        time.sleep(1 + attempt)
    die(f"could not fetch {url.split('?')[0]}: {type(last).__name__}: {last}")


def cached(name: str, url: str, max_age: int):
    """JSON from cache when fresh, else fetched and stored. Stale cache beats nothing."""
    os.makedirs(HOME, exist_ok=True)
    path = os.path.join(HOME, "cache", name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        if time.time() - os.path.getmtime(path) < max_age:
            with open(path) as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        pass
    try:
        data = fetch(url)
    except SystemExit:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        raise
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)
    return data


def load_config() -> dict:
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(cfg: dict) -> None:
    os.makedirs(HOME, exist_ok=True)
    tmp = CONFIG + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG)


# --- NFL data ----------------------------------------------------------------


def nfl_state() -> dict:
    return cached("state.json", f"{SLEEPER}/state/nfl", 1800)


def players() -> dict:
    """Compact player index. Sleeper asks that the full file be pulled at most daily."""
    path = os.path.join(HOME, "cache", "players_compact.json")
    try:
        if time.time() - os.path.getmtime(path) < 86400:
            with open(path) as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        pass
    raw = fetch(f"{SLEEPER}/players/nfl", timeout=120)
    compact = {}
    for pid, p in raw.items():
        pos = p.get("position")
        if pos not in POSITIONS:
            continue
        name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        compact[pid] = {
            "name": name,
            "pos": pos,
            "team": p.get("team"),
            "inj": p.get("injury_status"),
            "inj_part": p.get("injury_body_part"),
            "active": bool(p.get("active")),
            "age": p.get("age"),
            "exp": p.get("years_exp"),
        }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(compact, f)
    os.replace(path + ".tmp", path)
    return compact


def projections(season: str, week: int | None) -> dict:
    """player_id -> {'pts_ppr','pts_half_ppr','pts_std','opp'} for a week, or the season when week is None."""
    qs = "season_type=regular&" + "&".join(f"position%5B%5D={p}" for p in POSITIONS)
    if week is None:
        rows = cached(f"proj_{season}_season.json", f"{PROJ}/{season}?{qs}", 6 * 3600)
    else:
        rows = cached(f"proj_{season}_w{week}.json", f"{PROJ}/{season}/{week}?{qs}", 3 * 3600)
    out = {}
    for r in rows or []:
        st = r.get("stats") or {}
        out[str(r.get("player_id"))] = {
            "pts_ppr": st.get("pts_ppr"),
            "pts_half_ppr": st.get("pts_half_ppr"),
            "pts_std": st.get("pts_std"),
            "gp": st.get("gp"),
            "opp": r.get("opponent"),
        }
    return out


def trending(kind: str = "add") -> dict:
    rows = cached(f"trending_{kind}.json", f"{SLEEPER}/players/nfl/trending/{kind}?lookback_hours=24&limit=100", 3600)
    return {str(r["player_id"]): r["count"] for r in rows or []}


def espn_injuries() -> dict:
    """normalized player name -> {'status','comment'} from ESPN's league-wide report."""
    try:
        data = cached("espn_injuries.json", ESPN_INJURIES, 1800) or {}
    except SystemExit:
        return {}  # the ESPN notes are a bonus; Sleeper's designation still shows
    out = {}
    for team in data.get("injuries", []):
        for inj in team.get("injuries", []):
            ath = inj.get("athlete") or {}
            name = ath.get("displayName") or ""
            if name:
                out[norm(name)] = {"status": inj.get("status"), "comment": inj.get("shortComment") or ""}
    return out


# --- names -------------------------------------------------------------------


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def find_player(query: str, db: dict, prefer: set | None = None) -> tuple[str | None, list]:
    """Best player_id for a typed name; prefers players on `prefer` (e.g. my roster), then active ones."""
    q = norm(query)
    if not q:
        return None, []
    up = query.strip().upper()
    if up in db and db[up]["pos"] == "DEF":
        return up, []
    by_name: dict[str, list] = {}
    for pid, p in db.items():
        by_name.setdefault(norm(p["name"]), []).append(pid)
        if p["pos"] == "DEF":
            by_name.setdefault(norm(p["name"].split()[-1]) + " dst", []).append(pid)

    def rank(pids):
        return sorted(pids, key=lambda pid: (not (prefer and pid in prefer), not db[pid]["active"], db[pid]["team"] is None))

    if q in by_name:
        return rank(by_name[q])[0], []
    live = [pid for pid, p in db.items() if p["active"] and p["team"]]
    if " " not in q:
        # One word ("Chase", "Bijan", "Chse"): first or last name, typo-tolerant.
        # Several real candidates is a question for the owner, never a guess.
        tokens: dict[str, list] = {}
        for pid in live:
            for t in norm(db[pid]["name"]).split():
                tokens.setdefault(t, []).append(pid)
        keys = [q] if q in tokens else difflib.get_close_matches(q, tokens.keys(), n=3, cutoff=0.75)
        hits = list(dict.fromkeys(pid for k in keys for pid in tokens[k]))
        mine = [pid for pid in hits if prefer and pid in prefer]
        if len(mine) == 1:
            return mine[0], []
        if len(hits) == 1:
            return hits[0], []
        return None, [f"{db[pid]['name']} ({db[pid]['pos']}, {db[pid]['team']})" for pid in (mine or hits)[:8]]
    close = difflib.get_close_matches(q, by_name.keys(), n=5, cutoff=0.72)
    if not close:
        return None, []
    best = rank(by_name[close[0]])[0]
    return best, [c for c in close[1:]]


# --- league ------------------------------------------------------------------


def scoring_key(league: dict | None) -> str:
    rec = ((league or {}).get("scoring_settings") or {}).get("rec", 1.0)
    if rec >= 1:
        return "pts_ppr"
    if rec >= 0.5:
        return "pts_half_ppr"
    return "pts_std"


def scoring_label(key: str) -> str:
    return {"pts_ppr": "PPR", "pts_half_ppr": "Half-PPR", "pts_std": "Standard"}[key]


def league_bundle(cfg: dict, league_id: str | None = None) -> dict:
    lid = league_id or cfg.get("league_id")
    if not lid:
        die("no league linked yet -- run: commish.py link <sleeper_username>")
    league = cached(f"league_{lid}.json", f"{SLEEPER}/league/{lid}", 3600)
    if not league:
        die(f"Sleeper has no league {lid}")
    rosters = cached(f"rosters_{lid}.json", f"{SLEEPER}/league/{lid}/rosters", 600)
    users = cached(f"users_{lid}.json", f"{SLEEPER}/league/{lid}/users", 3600)
    names = {u["user_id"]: (u.get("metadata") or {}).get("team_name") or u.get("display_name") for u in users or []}
    mine = next((r for r in rosters or [] if r.get("owner_id") == cfg.get("user_id")
                 or cfg.get("user_id") in (r.get("co_owners") or [])), None)
    return {"league": league, "rosters": rosters or [], "names": names, "mine": mine}


def fmt_player(pid: str, db: dict, proj: dict, key: str, extra: str = "") -> str:
    p = db.get(pid) or {"name": pid, "pos": "?", "team": None, "inj": None}
    pr = proj.get(pid) or {}
    pts = pr.get(key)
    opp = pr.get("opp")
    inj = f" [{p['inj']}{' - ' + p['inj_part'] if p.get('inj_part') else ''}]" if p.get("inj") else ""
    if opp:
        matchup = f" vs {opp}"
    elif not p.get("team"):
        matchup = " (no NFL team)"
    elif p.get("inj") in ("IR", "Out", "PUP", "Sus", "NA"):
        matchup = " (not expected to play)"
    else:
        matchup = " (bye or no projection)"
    proj_s = f"{pts:.1f} proj" if isinstance(pts, (int, float)) else "no proj"
    return f"{p['name']} ({p['pos']}, {p.get('team') or 'FA'}){matchup} - {proj_s}{inj}{extra}"


# --- commands ----------------------------------------------------------------


def cmd_link(a):
    user = fetch(f"{SLEEPER}/user/{urllib.parse.quote(a.username)}")
    if not user or not user.get("user_id"):
        die(f"no Sleeper user named '{a.username}' -- check the spelling (it is the Sleeper username, not an email)")
    season = nfl_state()["league_season"]
    leagues = fetch(f"{SLEEPER}/user/{user['user_id']}/leagues/nfl/{season}") or []
    cfg = load_config()
    cfg.update({
        "username": user.get("username") or a.username,
        "display_name": user.get("display_name"),
        "user_id": user["user_id"],
        "season": season,
        "leagues": [{"league_id": l["league_id"], "name": l.get("name"), "teams": l.get("total_rosters"),
                     "scoring": scoring_label(scoring_key(l)), "status": l.get("status")} for l in leagues],
    })
    if len(leagues) == 1:
        cfg["league_id"] = leagues[0]["league_id"]
    elif cfg.get("league_id") not in {l["league_id"] for l in leagues}:
        cfg.pop("league_id", None)
    save_config(cfg)
    print(f"Linked Sleeper user {cfg['display_name']} ({cfg['user_id']}), season {season}.")
    if not leagues:
        print("This account has no NFL leagues this season on Sleeper.")
    for l in cfg["leagues"]:
        mark = "  <- default" if l["league_id"] == cfg.get("league_id") else ""
        print(f"- {l['name']} | {l['teams']} teams | {l['scoring']} | {l['status']} | league_id {l['league_id']}{mark}")
    if len(leagues) > 1 and not cfg.get("league_id"):
        print("Several leagues: ask which one to focus on, then run: commish.py use <league_id>")


def cmd_use(a):
    cfg = load_config()
    ids = {l["league_id"]: l for l in cfg.get("leagues", [])}
    if a.league_id not in ids:
        die(f"league {a.league_id} is not one of this account's leagues: {', '.join(ids) or 'none linked'}")
    cfg["league_id"] = a.league_id
    save_config(cfg)
    print(f"Default league: {ids[a.league_id]['name']} ({a.league_id})")


def cmd_status(a):
    st = nfl_state()
    cfg = load_config()
    print(f"NFL {st['season']} {st['season_type']} season, week {st['display_week']}.")
    if not cfg.get("user_id"):
        print("No Sleeper account linked. Onboarding: ask for their Sleeper username (commish-setup).")
        return
    print(f"Linked: {cfg.get('display_name')} (@{cfg.get('username')}).")
    for l in cfg.get("leagues", []):
        mark = "  <- default" if l["league_id"] == cfg.get("league_id") else ""
        print(f"- {l['name']} | {l['teams']} teams | {l['scoring']} | league_id {l['league_id']}{mark}")


def cmd_team(a):
    cfg = load_config()
    b = league_bundle(cfg, a.league)
    if not b["mine"]:
        die("could not find the owner's roster in this league")
    st = nfl_state()
    db, key = players(), scoring_key(b["league"])
    proj = projections(st["season"], st["display_week"])
    mine = b["mine"]
    starters = [s for s in mine.get("starters") or [] if s and s != "0"]
    bench = [p for p in mine.get("players") or [] if p not in starters and p not in (mine.get("reserve") or [])]
    s = mine.get("settings") or {}
    print(f"{b['league']['name']} - week {st['display_week']} - {scoring_label(key)} scoring")
    print(f"Record {s.get('wins', 0)}-{s.get('losses', 0)}{'-' + str(s['ties']) if s.get('ties') else ''}, "
          f"points for {s.get('fpts', 0)}")
    print("STARTERS:")
    slots = [x for x in b["league"].get("roster_positions") or [] if x not in ("BN", "IR", "TAXI")]
    for i, pid in enumerate(mine.get("starters") or []):
        slot = slots[i] if i < len(slots) else "?"
        print(f"  {slot}: " + (fmt_player(pid, db, proj, key) if pid and pid != "0" else "EMPTY SLOT"))
    total = sum((proj.get(p) or {}).get(key) or 0 for p in starters)
    print(f"  projected starters total: {total:.1f}")
    print("BENCH:")
    for pid in sorted(bench, key=lambda p: -((proj.get(p) or {}).get(key) or 0)):
        print("  " + fmt_player(pid, db, proj, key))
    if mine.get("reserve"):
        print("IR:")
        for pid in mine["reserve"]:
            print("  " + fmt_player(pid, db, proj, key))


def cmd_matchup(a):
    cfg = load_config()
    b = league_bundle(cfg, a.league)
    st = nfl_state()
    week = st["display_week"]
    db, key = players(), scoring_key(b["league"])
    proj = projections(st["season"], week)
    matchups = fetch(f"{SLEEPER}/league/{b['league']['league_id']}/matchups/{week}") or []
    me = next((m for m in matchups if b["mine"] and m["roster_id"] == b["mine"]["roster_id"]), None)
    if not me:
        die(f"no matchup for the owner in week {week} (bye week, playoffs not reached, or league not drafted)")
    opp = next((m for m in matchups if m.get("matchup_id") == me.get("matchup_id") and m["roster_id"] != me["roster_id"]), None)
    owner_of = {r["roster_id"]: r.get("owner_id") for r in b["rosters"]}

    def side(m, label):
        starters = [p for p in m.get("starters") or [] if p and p != "0"]
        projected = sum((proj.get(p) or {}).get(key) or 0 for p in starters)
        print(f"{label}: {b['names'].get(owner_of.get(m['roster_id']), 'unknown')} - "
              f"live points {m.get('points') or 0:.1f}, projected starters {projected:.1f}")
        for p in starters:
            live = (m.get("players_points") or {}).get(p)
            print("  " + fmt_player(p, db, proj, key, f" | live {live:.1f}" if isinstance(live, (int, float)) and live else ""))

    print(f"Week {week} matchup - {scoring_label(key)}")
    side(me, "YOU")
    if opp:
        side(opp, "OPPONENT")
    else:
        print("No opponent this week.")


def cmd_startsit(a):
    cfg = load_config()
    st = nfl_state()
    db = players()
    b = league_bundle(cfg, a.league) if cfg.get("league_id") or a.league else None
    key = scoring_key(b["league"]) if b else "pts_ppr"
    mine = set((b or {}).get("mine", {}) and b["mine"].get("players") or [])
    proj = projections(st["season"], st["display_week"])
    inj = espn_injuries()
    hot = trending("add")
    print(f"Week {st['display_week']} start/sit - {scoring_label(key)}{'' if b else ' (no league linked, assuming PPR)'}")
    rows = []
    for q in a.names:
        pid, alts = find_player(q, db, mine)
        if not pid:
            print(f"? '{q}': no confident match" + (f" - did they mean: {', '.join(alts)}" if alts else ""))
            continue
        pts = (proj.get(pid) or {}).get(key)
        rows.append((pts if isinstance(pts, (int, float)) else -1, pid))
    for pts, pid in sorted(rows, reverse=True):
        p = db[pid]
        extra = ""
        e = inj.get(norm(p["name"]))
        if e:
            extra += f" | ESPN: {e['status']} - {e['comment']}"
        if pid in hot:
            extra += f" | trending: added in {hot[pid]:,} leagues (24h)"
        if b and pid not in mine:
            extra += " | not on your roster"
        print("- " + fmt_player(pid, db, proj, key, extra))


def cmd_waivers(a):
    cfg = load_config()
    b = league_bundle(cfg, a.league)
    st = nfl_state()
    db, key = players(), scoring_key(b["league"])
    proj = projections(st["season"], st["display_week"])
    season = projections(st["season"], None)
    hot = trending("add")
    rostered = {p for r in b["rosters"] for p in (r.get("players") or [])}
    want = {x.strip().upper() for x in a.pos.split(",")} if a.pos else set(POSITIONS) - {"K", "DEF"}
    pool = []
    for pid, p in db.items():
        if pid in rostered or p["pos"] not in want or not p.get("team"):
            continue
        wk = (proj.get(pid) or {}).get(key) or 0
        ros = (season.get(pid) or {}).get(key) or 0
        if wk <= 0 and pid not in hot:
            continue
        pool.append((wk + ros / 17.0 + min(hot.get(pid, 0), 50000) / 10000.0, pid, ros))
    pool.sort(reverse=True)
    per_pos = a.limit if len(want) == 1 else max(2, a.limit // len(want) + 1)
    shown, counts = [], {}
    for row in pool:
        pos = db[row[1]]["pos"]
        if counts.get(pos, 0) < per_pos:
            counts[pos] = counts.get(pos, 0) + 1
            shown.append(row)
    shown.sort(key=lambda r: (POSITIONS.index(db[r[1]]["pos"]), -r[0]))
    print(f"Best available in {b['league']['name']} - week {st['display_week']} - {scoring_label(key)} "
          f"(positions: {', '.join(sorted(want))})")
    if (b["league"].get("settings") or {}).get("waiver_budget"):
        mine = b["mine"] or {}
        budget = b["league"]["settings"]["waiver_budget"] - ((mine.get("settings") or {}).get("waiver_budget_used") or 0)
        print(f"FAAB remaining for you: ${budget}")
    for _, pid, ros in shown:
        extra = f" | season proj {ros:.0f}" if ros else ""
        if pid in hot:
            extra += f" | added in {hot[pid]:,} leagues (24h)"
        print("- " + fmt_player(pid, db, proj, key, extra))


def cmd_trade(a):
    cfg = load_config()
    st = nfl_state()
    db = players()
    b = league_bundle(cfg, a.league) if cfg.get("league_id") or a.league else None
    key = scoring_key(b["league"]) if b else "pts_ppr"
    mine = set(b["mine"].get("players") or []) if b and b["mine"] else set()
    wk = projections(st["season"], st["display_week"])
    season = projections(st["season"], None)
    inj = espn_injuries()
    weeks_left = max(1, 18 - int(st["display_week"]) + 1)

    def side(label, text, prefer):
        total_season = total_week = 0.0
        best = 0.0
        print(f"{label}:")
        for q in [x.strip() for x in text.split(",") if x.strip()]:
            pid, alts = find_player(q, db, prefer)
            if not pid:
                print(f"  ? '{q}': no confident match" + (f" - maybe {', '.join(alts)}" if alts else ""))
                continue
            sp = (season.get(pid) or {}).get(key) or 0
            gp = (season.get(pid) or {}).get("gp") or 17
            per_game = sp / gp if gp else 0
            total_season += per_game * weeks_left
            best = max(best, per_game)
            total_week += (wk.get(pid) or {}).get(key) or 0
            p = db[pid]
            e = inj.get(norm(p["name"]))
            note = f" | ESPN: {e['status']} - {e['comment']}" if e else ""
            print(f"  {p['name']} ({p['pos']}, {p.get('team') or 'FA'}, age {p.get('age') or '?'}) - "
                  f"{per_game:.1f} proj/game, ~{per_game * weeks_left:.0f} pts rest of season"
                  f"{' [' + p['inj'] + ']' if p.get('inj') else ''}{note}")
        print(f"  TOTAL: ~{total_season:.0f} rest-of-season pts, {total_week:.1f} this week; best player {best:.1f}/game")
        return total_season, best

    print(f"Trade check - {scoring_label(key)} - {weeks_left} regular-season weeks left (from season projections)")
    give, give_best = side("YOU GIVE", a.give, mine)
    get, get_best = side("YOU GET", a.get, None)
    diff = get - give
    print(f"Net rest-of-season projection: {'+' if diff >= 0 else ''}{diff:.0f} pts for you; "
          f"best player in the deal: {'you get' if get_best > give_best else 'you give'} the stronger one "
          f"({max(get_best, give_best):.1f} vs {min(get_best, give_best):.1f}/game).")
    print("Only starters score: a bench player adds totals but rarely lineup points. "
          "Projections ignore roster fit, positional scarcity and bye weeks -- weigh those too.")


def cmd_player(a):
    st = nfl_state()
    db = players()
    pid, alts = find_player(a.name, db)
    if not pid:
        die(f"no confident match for '{a.name}'" + (f" - maybe {', '.join(alts)}" if alts else ""))
    cfg = load_config()
    b = league_bundle(cfg) if cfg.get("league_id") else None
    key = scoring_key(b["league"]) if b else "pts_ppr"
    wk = projections(st["season"], st["display_week"])
    season = projections(st["season"], None)
    p = db[pid]
    print(fmt_player(pid, db, wk, key))
    sp = (season.get(pid) or {}).get(key)
    if sp:
        print(f"Season projection: {sp:.0f} {scoring_label(key)} pts")
    print(f"Age {p.get('age') or '?'}, {p.get('exp') if p.get('exp') is not None else '?'} years in the NFL")
    e = espn_injuries().get(norm(p["name"]))
    if e:
        print(f"ESPN injury report: {e['status']} - {e['comment']}")
    hot = trending("add")
    if pid in hot:
        print(f"Trending: added in {hot[pid]:,} Sleeper leagues in the last 24h")
    if b:
        owner = next((r for r in b["rosters"] if pid in (r.get("players") or [])), None)
        if owner is None:
            print("In your league: available (free agent / waivers)")
        elif b["mine"] and owner["roster_id"] == b["mine"]["roster_id"]:
            print("In your league: on YOUR roster")
        else:
            print(f"In your league: rostered by {b['names'].get(owner.get('owner_id'), 'another team')}")


def roster_injuries(cfg: dict) -> list[tuple[str, str, str, bool]]:
    b = league_bundle(cfg)
    if not b["mine"]:
        return []
    db = players()
    starters = set(b["mine"].get("starters") or [])
    out = []
    for pid in b["mine"].get("players") or []:
        p = db.get(pid)
        if p and p.get("inj"):
            out.append((p["name"], p["pos"], p["inj"], pid in starters))
    return sorted(out, key=lambda x: (not x[3], x[0]))


def cmd_injuries(a):
    cfg = load_config()
    rows = roster_injuries(cfg)
    if not rows:
        print("No injury designations on your roster right now.")
        return
    inj = espn_injuries()
    for name, pos, status, starting in rows:
        e = inj.get(norm(name))
        note = f" - {e['comment']}" if e and e.get("comment") else ""
        print(f"- {name} ({pos}) {status}{' - IN YOUR STARTING LINEUP' if starting else ' - bench'}{note}")


def cmd_monitor(a):
    """Byte-stable output for `hermes cron --monitor-script`: changes only when a designation does."""
    cfg = load_config()
    if not cfg.get("league_id"):
        return  # nothing linked: empty and stable, the alert never fires
    for name, pos, status, starting in roster_injuries(cfg):
        print(f"{name}|{pos}|{status}|{'starter' if starting else 'bench'}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="commish.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("link"); s.add_argument("username"); s.set_defaults(fn=cmd_link)
    s = sub.add_parser("use"); s.add_argument("league_id"); s.set_defaults(fn=cmd_use)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    for name, fn in (("team", cmd_team), ("matchup", cmd_matchup), ("injuries", cmd_injuries)):
        s = sub.add_parser(name); s.add_argument("--league"); s.set_defaults(fn=fn)
    s = sub.add_parser("startsit"); s.add_argument("names", nargs="+"); s.add_argument("--league"); s.set_defaults(fn=cmd_startsit)
    s = sub.add_parser("waivers"); s.add_argument("--pos"); s.add_argument("--limit", type=int, default=10)
    s.add_argument("--league"); s.set_defaults(fn=cmd_waivers)
    s = sub.add_parser("trade"); s.add_argument("--give", required=True); s.add_argument("--get", required=True)
    s.add_argument("--league"); s.set_defaults(fn=cmd_trade)
    s = sub.add_parser("player"); s.add_argument("name"); s.set_defaults(fn=cmd_player)
    sub.add_parser("monitor").set_defaults(fn=cmd_monitor)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
