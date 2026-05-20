# seed_demo.py
# Populates nba.db and mlb.db with realistic demo data so the app looks
# fully functional on Streamlit Cloud (no live data collection needed).
# Called at app startup — no-ops if data already present.

import sqlite3
import numpy as np
import random
from datetime import date, timedelta, datetime
from pathlib import Path
from config import DB_PATH

MLB_DB = str(Path(__file__).parent / "mlb.db")

# ── Roster / schedule constants ────────────────────────────────────────────────

NBA_TEAMS = [
    ("Boston Celtics",       "BOS"), ("Miami Heat",            "MIA"),
    ("Milwaukee Bucks",      "MIL"), ("Cleveland Cavaliers",   "CLE"),
    ("New York Knicks",      "NYK"), ("Indiana Pacers",        "IND"),
    ("Oklahoma City Thunder","OKC"), ("Denver Nuggets",        "DEN"),
    ("Los Angeles Lakers",   "LAL"), ("Golden State Warriors", "GSW"),
    ("Memphis Grizzlies",    "MEM"), ("Dallas Mavericks",      "DAL"),
    ("Phoenix Suns",         "PHX"), ("Sacramento Kings",      "SAC"),
    ("Los Angeles Clippers", "LAC"),
]

MLB_TEAMS = [
    ("New York Yankees",      "NYY"), ("Boston Red Sox",        "BOS"),
    ("Los Angeles Dodgers",   "LAD"), ("Houston Astros",        "HOU"),
    ("Atlanta Braves",        "ATL"), ("Chicago Cubs",          "CHC"),
    ("San Diego Padres",      "SDP"), ("Baltimore Orioles",     "BAL"),
    ("Texas Rangers",         "TEX"), ("Cleveland Guardians",   "CLE"),
]

NBA_PLAYERS = [
    # (name, team_abbrev, team_id, avg_pts, avg_reb, avg_ast, avg_min)
    ("Jayson Tatum",      "BOS", 1610612738, 26.9, 8.1, 4.9, 36.2),
    ("Jaylen Brown",      "BOS", 1610612738, 23.0, 5.5, 3.6, 33.8),
    ("Giannis Antetokounmpo", "MIL", 1610612749, 30.4, 11.5, 5.8, 33.1),
    ("Damian Lillard",    "MIL", 1610612749, 24.3, 4.4, 7.0, 34.5),
    ("Donovan Mitchell",  "CLE", 1610612739, 26.0, 4.7, 5.1, 34.9),
    ("Jalen Brunson",     "NYK", 1610612752, 28.7, 3.6, 6.7, 35.8),
    ("Karl-Anthony Towns","NYK", 1610612752, 24.2, 13.9, 3.1, 34.0),
    ("Shai Gilgeous-Alexander", "OKC", 1610612760, 31.4, 5.5, 6.2, 34.7),
    ("Nikola Jokic",      "DEN", 1610612743, 26.4, 12.4, 9.0, 33.9),
    ("Jamal Murray",      "DEN", 1610612743, 21.2, 4.1, 6.5, 33.0),
    ("LeBron James",      "LAL", 1610612747, 25.7, 7.3, 8.3, 35.1),
    ("Anthony Davis",     "LAL", 1610612747, 24.9, 12.6, 3.5, 35.4),
    ("Stephen Curry",     "GSW", 1610612744, 26.4, 4.5, 5.1, 32.8),
    ("Luka Doncic",       "DAL", 1610612742, 33.9, 9.2, 9.8, 36.3),
    ("Kevin Durant",      "PHX", 1610612756, 27.1, 6.6, 5.0, 35.0),
    ("Devin Booker",      "PHX", 1610612756, 27.1, 4.5, 6.9, 35.2),
    ("De'Aaron Fox",      "SAC", 1610612758, 25.2, 4.1, 5.9, 33.7),
    ("Tyrese Haliburton", "IND", 1610612754, 20.1, 3.9, 10.9, 33.2),
    ("Bam Adebayo",       "MIA", 1610612748, 19.3, 10.4, 3.5, 33.8),
    ("Jaren Jackson Jr.", "MEM", 1610612763, 22.3, 6.5, 2.1, 31.4),
]

MLB_PITCHERS = [
    "Gerrit Cole", "Shane Bieber", "Clayton Kershaw", "Freddie Peralta",
    "Spencer Strider", "Justin Verlander", "Max Scherzer", "Blake Snell",
    "Zack Wheeler", "Logan Webb",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _rng(seed=42):
    random.seed(seed)
    np.random.seed(seed)

def _is_seeded(path, table, min_rows=10):
    if not Path(path).exists():
        return False
    try:
        conn = sqlite3.connect(path)
        n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        conn.close()
        return n >= min_rows
    except Exception:
        return False

def _american_odds(prob):
    prob = max(0.01, min(0.99, prob))
    if prob >= 0.5:
        return round(-prob / (1 - prob) * 100)
    return round((1 - prob) / prob * 100)

def _payout(american_odds):
    if american_odds > 0:
        return american_odds / 100
    return 100 / abs(american_odds)

def _game_id(dt, home_abbr, away_abbr):
    return f"{dt.strftime('%Y%m%d')}_{away_abbr}_{home_abbr}"


# ── NBA seeding ────────────────────────────────────────────────────────────────

def _seed_nba(conn):
    today = date.today()

    # ── Player game logs ──────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_game_logs (
            player_id INTEGER, player_name TEXT, team_id INTEGER,
            team_abbreviation TEXT, game_id TEXT, game_date TEXT,
            season TEXT, matchup TEXT, is_home INTEGER, wl TEXT,
            min_played REAL, pts REAL, reb REAL, ast REAL,
            stl REAL, blk REAL, tov REAL, fg3m REAL,
            PRIMARY KEY (player_id, game_id)
        )
    """)

    log_rows = []
    for player_id, (name, abbr, team_id, ppg, rpg, apg, mpg) in enumerate(NBA_PLAYERS, start=1):
        opponents = [t for t in NBA_TEAMS if t[1] != abbr]
        for g in range(30):
            gdate = today - timedelta(days=30 - g)
            opp   = opponents[g % len(opponents)]
            is_home = g % 2
            matchup = f"{abbr} {'vs.' if is_home else '@'} {opp[1]}"
            wl   = "W" if random.random() < 0.54 else "L"
            mins = max(8.0, np.random.normal(mpg, 3.0))
            pts  = max(0.0, np.random.normal(ppg, 6.0))
            reb  = max(0.0, np.random.normal(rpg, 2.5))
            ast  = max(0.0, np.random.normal(apg, 2.0))
            stl  = max(0.0, np.random.normal(1.0, 0.8))
            blk  = max(0.0, np.random.normal(0.6, 0.6))
            tov  = max(0.0, np.random.normal(2.5, 1.2))
            fg3m = max(0.0, np.random.normal(2.2, 1.5))
            gid  = _game_id(gdate, abbr if is_home else opp[1],
                            opp[1] if is_home else abbr)
            log_rows.append((
                player_id, name, team_id, abbr, gid,
                gdate.isoformat(), "2025-26", matchup, is_home, wl,
                round(mins, 1), round(pts, 1), round(reb, 1), round(ast, 1),
                round(stl, 1), round(blk, 1), round(tov, 1), int(fg3m),
            ))

    conn.executemany("""
        INSERT OR IGNORE INTO player_game_logs
        (player_id, player_name, team_id, team_abbreviation, game_id, game_date,
         season, matchup, is_home, wl, min_played, pts, reb, ast, stl, blk, tov, fg3m)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, log_rows)

    # ── Historical bet logs (90 days) ─────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bet_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            predict_date TEXT, game_id TEXT,
            home_team TEXT, away_team TEXT,
            bet_side TEXT, bet_team TEXT,
            model_prob REAL, fair_prob REAL, edge REAL,
            line REAL, kelly_stake REAL,
            result TEXT, profit_units REAL, clv REAL,
            notes TEXT, recorded_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ats_bet_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            predict_date TEXT, game_id TEXT,
            home_team TEXT, away_team TEXT,
            bet_side TEXT, bet_team TEXT,
            spread REAL, pred_margin REAL,
            cover_prob REAL, edge REAL,
            line REAL, kelly_stake REAL,
            result TEXT, profit_units REAL, clv REAL,
            recorded_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS totals_bet_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            predict_date TEXT, game_id TEXT,
            home_team TEXT, away_team TEXT,
            bet_side TEXT, total_line REAL, pred_total REAL,
            ou_prob REAL, edge REAL,
            line REAL, kelly_stake REAL,
            result TEXT, profit_units REAL, clv REAL,
            recorded_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS props_bet_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            predict_date TEXT, game_id TEXT,
            player_name TEXT, home_team TEXT, away_team TEXT,
            bet_side TEXT, line REAL, pred_pts REAL,
            ou_prob REAL, edge REAL,
            price REAL, kelly_stake REAL,
            result TEXT, profit_units REAL, recorded_at TEXT
        )
    """)

    ml_rows, ats_rows, tot_rows, prop_rows = [], [], [], []
    matchup_pool = list(range(0, len(NBA_TEAMS) - 1, 2))

    for day_offset in range(90, 0, -1):
        d = today - timedelta(days=day_offset)
        # ~4 games on average every 2 days
        if random.random() < 0.55:
            continue
        n_games = random.randint(2, 5)
        pairs = random.sample(range(len(NBA_TEAMS)), min(n_games * 2, len(NBA_TEAMS)))
        for i in range(0, len(pairs) - 1, 2):
            home = NBA_TEAMS[pairs[i]]
            away = NBA_TEAMS[pairs[i + 1]]
            gid  = _game_id(d, home[1], away[1])
            dstr = d.isoformat()

            # ── ML bet ──
            true_prob = np.random.uniform(0.50, 0.72)
            side      = "home" if true_prob > 0.5 else "away"
            fair_prob = true_prob - np.random.uniform(0.02, 0.05)
            edge      = true_prob - fair_prob
            if edge >= 0.03 and random.random() < 0.65:
                odds   = _american_odds(fair_prob)
                kelly  = round(edge * 0.25, 4)
                won    = random.random() < true_prob
                result = "WIN" if won else "LOSS"
                pnl    = round(kelly * _payout(odds), 4) if won else round(-kelly, 4)
                clv    = round(np.random.normal(0.01, 0.02), 4)
                team   = home[0] if side == "home" else away[0]
                ml_rows.append((
                    dstr, gid, home[0], away[0], side, team,
                    round(true_prob, 4), round(fair_prob, 4), round(edge, 4),
                    odds, kelly, result, pnl, clv, None,
                    datetime.now().isoformat()
                ))

            # ── ATS bet ──
            pred_margin = np.random.normal(0, 6)
            spread      = round(pred_margin - np.random.uniform(-1, 3), 1)
            cover_prob  = np.random.uniform(0.50, 0.68)
            ats_edge    = cover_prob - np.random.uniform(0.44, 0.48)
            if ats_edge >= 0.04 and random.random() < 0.55:
                ats_side = "home" if cover_prob > 0.5 else "away"
                odds     = _american_odds(0.476)  # ~-110
                kelly    = round(ats_edge * 0.25, 4)
                won      = random.random() < cover_prob
                result   = "WIN" if won else "LOSS"
                pnl      = round(kelly * _payout(odds), 4) if won else round(-kelly, 4)
                clv      = round(np.random.normal(0.005, 0.015), 4)
                team     = home[0] if ats_side == "home" else away[0]
                sp       = -spread if ats_side == "home" else spread
                ats_rows.append((
                    dstr, gid, home[0], away[0], ats_side, team,
                    round(sp, 1), round(pred_margin, 1),
                    round(cover_prob, 4), round(ats_edge, 4),
                    odds, kelly, result, pnl, clv,
                    datetime.now().isoformat()
                ))

            # ── Totals bet ──
            total_line  = round(np.random.uniform(215, 235), 1)
            pred_total  = total_line + np.random.normal(0, 4)
            over_prob   = np.random.uniform(0.50, 0.65)
            tot_edge    = over_prob - np.random.uniform(0.44, 0.48)
            if tot_edge >= 0.04 and random.random() < 0.45:
                t_side = "over" if over_prob > 0.5 else "under"
                odds   = _american_odds(0.476)
                kelly  = round(tot_edge * 0.25, 4)
                won    = random.random() < over_prob
                result = "WIN" if won else "LOSS"
                pnl    = round(kelly * _payout(odds), 4) if won else round(-kelly, 4)
                clv    = round(np.random.normal(0.005, 0.015), 4)
                tot_rows.append((
                    dstr, gid, home[0], away[0], t_side,
                    round(total_line, 1), round(pred_total, 1),
                    round(over_prob, 4), round(tot_edge, 4),
                    odds, kelly, result, pnl, clv,
                    datetime.now().isoformat()
                ))

    # ── Props bets ──
    for day_offset in range(60, 1, -1):
        d = today - timedelta(days=day_offset)
        if random.random() < 0.6:
            continue
        player = random.choice(NBA_PLAYERS)
        pname, abbr, _, ppg, *_ = player
        line      = round(ppg + np.random.normal(0, 1.5), 1)
        pred_pts  = round(ppg + np.random.normal(0, 2), 1)
        over_prob = 0.5 + (pred_pts - line) / 12
        over_prob = max(0.35, min(0.80, over_prob))
        edge      = over_prob - np.random.uniform(0.44, 0.48)
        if abs(edge) >= 0.08:
            b_side = "over" if edge > 0 else "under"
            prob   = over_prob if b_side == "over" else 1 - over_prob
            odds   = _american_odds(0.476)
            kelly  = round(abs(edge) * 0.25, 4)
            won    = random.random() < prob
            result = "WIN" if won else "LOSS"
            pnl    = round(kelly * _payout(odds), 4) if won else round(-kelly, 4)
            gid    = f"{d.strftime('%Y%m%d')}_PROP_{abbr}"
            prop_rows.append((
                d.isoformat(), gid, pname, "—", "—",
                b_side, round(line, 1), round(pred_pts, 1),
                round(prob, 4), round(abs(edge), 4),
                odds, kelly, result, pnl,
                datetime.now().isoformat()
            ))

    conn.executemany(
        "INSERT INTO bet_log (predict_date,game_id,home_team,away_team,bet_side,bet_team,"
        "model_prob,fair_prob,edge,line,kelly_stake,result,profit_units,clv,notes,recorded_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ml_rows
    )
    conn.executemany(
        "INSERT INTO ats_bet_log (predict_date,game_id,home_team,away_team,bet_side,bet_team,"
        "spread,pred_margin,cover_prob,edge,line,kelly_stake,result,profit_units,clv,recorded_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ats_rows
    )
    conn.executemany(
        "INSERT INTO totals_bet_log (predict_date,game_id,home_team,away_team,bet_side,"
        "total_line,pred_total,ou_prob,edge,line,kelly_stake,result,profit_units,clv,recorded_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", tot_rows
    )
    conn.executemany(
        "INSERT INTO props_bet_log (predict_date,game_id,player_name,home_team,away_team,"
        "bet_side,line,pred_pts,ou_prob,edge,price,kelly_stake,result,profit_units,recorded_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", prop_rows
    )

    # ── Today's predictions ───────────────────────────────────────────────────
    today_str = today.isoformat()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            game_id TEXT, predict_date TEXT,
            home_team TEXT, away_team TEXT, commence_time TEXT,
            model_home_prob REAL, model_away_prob REAL,
            home_fair_prob REAL, away_fair_prob REAL,
            home_edge REAL, away_edge REAL,
            home_value INTEGER, away_value INTEGER,
            home_kelly REAL, away_kelly REAL,
            bookmaker TEXT, home_price REAL, away_price REAL,
            actual_home_win INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS spread_predictions (
            game_id TEXT, predict_date TEXT,
            home_team TEXT, away_team TEXT, commence_time TEXT,
            home_point REAL, away_point REAL,
            pred_home_margin REAL,
            home_cover_prob REAL, away_cover_prob REAL,
            home_cover_fair REAL, away_cover_fair REAL,
            home_ats_edge REAL, away_ats_edge REAL,
            home_ats_value INTEGER, away_ats_value INTEGER,
            home_ats_kelly REAL, away_ats_kelly REAL,
            home_price REAL, away_price REAL,
            spread_sigma REAL, bookmaker TEXT, actual_home_cover INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS props_predictions (
            player_name TEXT, game_id TEXT, predict_date TEXT,
            home_team TEXT, away_team TEXT, commence_time TEXT,
            bookmaker TEXT, line REAL, pred_pts REAL,
            over_prob REAL, under_prob REAL,
            over_fair REAL, under_fair REAL,
            over_edge REAL, under_edge REAL,
            over_value INTEGER, under_value INTEGER,
            over_kelly REAL, under_kelly REAL,
            over_price REAL, under_price REAL,
            props_sigma REAL, actual_pts REAL,
            PRIMARY KEY (player_name, game_id, predict_date)
        )
    """)

    conn.execute(f"DELETE FROM predictions WHERE predict_date='{today_str}'")
    conn.execute(f"DELETE FROM spread_predictions WHERE predict_date='{today_str}'")
    conn.execute(f"DELETE FROM props_predictions WHERE predict_date='{today_str}'")

    today_games = [
        ("Boston Celtics",        "Milwaukee Bucks",      "19:30"),
        ("Oklahoma City Thunder", "Cleveland Cavaliers",  "20:00"),
        ("Denver Nuggets",        "Los Angeles Lakers",   "21:30"),
        ("New York Knicks",       "Indiana Pacers",       "20:30"),
        ("Golden State Warriors", "Phoenix Suns",         "22:00"),
        ("Memphis Grizzlies",     "Dallas Mavericks",     "20:00"),
    ]

    pred_rows  = []
    spread_rows = []
    for home_name, away_name, tip in today_games:
        home_abbr = next(t[1] for t in NBA_TEAMS if t[0] == home_name)
        away_abbr = next(t[1] for t in NBA_TEAMS if t[0] == away_name)
        gid   = _game_id(today, home_abbr, away_abbr)
        ct    = f"{today_str}T{tip}:00Z"
        hp    = round(np.random.uniform(0.50, 0.68), 4)
        ap    = round(1 - hp, 4)
        hfair = round(hp - np.random.uniform(0.02, 0.04), 4)
        afair = round(1 - hfair, 4)
        hedge = round(hp - hfair, 4)
        aedge = round(ap - afair, 4)
        hval  = 1 if hedge >= 0.04 else 0
        aval  = 1 if aedge >= 0.04 else 0
        hkelly = round(hedge * 0.25, 4) if hval else 0
        akelly = round(aedge * 0.25, 4) if aval else 0
        hprice = _american_odds(hfair)
        aprice = _american_odds(afair)
        pred_rows.append((
            gid, today_str, home_name, away_name, ct,
            hp, ap, hfair, afair, hedge, aedge,
            hval, aval, hkelly, akelly,
            "draftkings", hprice, aprice, None
        ))

        margin = np.random.normal(0, 6)
        hs = round(-margin + np.random.uniform(-0.5, 0.5), 1)
        as_ = -hs
        hcov = round(0.5 + margin / 20, 4)
        hcov = max(0.35, min(0.70, hcov))
        acov = round(1 - hcov, 4)
        he   = round(hcov - 0.476, 4)
        ae   = round(acov - 0.476, 4)
        spread_rows.append((
            gid, today_str, home_name, away_name, ct,
            hs, as_, round(margin, 1),
            hcov, acov, 0.5, 0.5,
            he, ae,
            1 if he >= 0.03 else 0, 1 if ae >= 0.03 else 0,
            round(he * 0.25, 4) if he >= 0.03 else 0,
            round(ae * 0.25, 4) if ae >= 0.03 else 0,
            _american_odds(0.476), _american_odds(0.476),
            8.5, "draftkings", None
        ))

    conn.executemany(
        "INSERT OR IGNORE INTO predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        pred_rows
    )
    conn.executemany(
        "INSERT OR IGNORE INTO spread_predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        spread_rows
    )

    # ── Today's props predictions ─────────────────────────────────────────────
    props_rows = []
    for i, (home_name, away_name, tip) in enumerate(today_games[:4]):
        home_abbr = next(t[1] for t in NBA_TEAMS if t[0] == home_name)
        away_abbr = next(t[1] for t in NBA_TEAMS if t[0] == away_name)
        gid = _game_id(today, home_abbr, away_abbr)
        ct  = f"{today_str}T{tip}:00Z"
        for player_name, abbr, *_ , ppg, _, _, _ in NBA_PLAYERS:
            if abbr not in (home_abbr, away_abbr):
                continue
            sigma    = 5.99
            line     = round(ppg + np.random.uniform(-1.5, 1.5), 1)
            pred_pts = round(ppg + np.random.normal(0, 1.5), 1)
            from scipy.stats import norm as _norm
            over_prob  = round(float(_norm.cdf((pred_pts - line) / sigma)), 4)
            under_prob = round(1 - over_prob, 4)
            over_fair  = round(np.random.uniform(0.48, 0.52), 4)
            under_fair = round(1 - over_fair, 4)
            over_edge  = round(over_prob - over_fair, 4)
            under_edge = round(under_prob - under_fair, 4)
            over_val   = 1 if over_edge >= 0.12 else 0
            under_val  = 1 if under_edge >= 0.12 else 0
            props_rows.append((
                player_name, gid, today_str, home_name, away_name, ct,
                "draftkings", line, pred_pts,
                over_prob, under_prob, over_fair, under_fair,
                over_edge, under_edge, over_val, under_val,
                round(over_edge * 0.25, 4) if over_val else 0,
                round(under_edge * 0.25, 4) if under_val else 0,
                -115, -105, sigma, None
            ))

    conn.executemany(
        "INSERT OR IGNORE INTO props_predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        props_rows
    )

    conn.commit()


# ── MLB seeding ────────────────────────────────────────────────────────────────

def _seed_mlb(conn):
    today = date.today()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_bet_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            predict_date TEXT, game_id TEXT,
            home_team TEXT, away_team TEXT,
            bet_side TEXT, bet_team TEXT,
            model_prob REAL, fair_prob REAL, edge REAL,
            line REAL, kelly_stake REAL,
            result TEXT, profit_units REAL, clv REAL,
            recorded_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_ats_bet_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            predict_date TEXT, game_id TEXT,
            home_team TEXT, away_team TEXT,
            bet_side TEXT, bet_team TEXT,
            spread REAL, pred_margin REAL,
            cover_prob REAL, edge REAL,
            line REAL, kelly_stake REAL,
            result TEXT, profit_units REAL, clv REAL,
            recorded_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_totals_bet_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            predict_date TEXT, game_id TEXT,
            home_team TEXT, away_team TEXT,
            bet_side TEXT, total_line REAL, pred_total REAL,
            ou_prob REAL, edge REAL,
            line REAL, kelly_stake REAL,
            result TEXT, profit_units REAL, clv REAL,
            recorded_at TEXT
        )
    """)

    ml_rows, ats_rows, tot_rows = [], [], []

    for day_offset in range(90, 0, -1):
        d = today - timedelta(days=day_offset)
        if random.random() < 0.25:
            continue
        n_games = random.randint(3, 8)
        pairs = random.sample(range(len(MLB_TEAMS)), min(n_games * 2, len(MLB_TEAMS)))
        for i in range(0, len(pairs) - 1, 2):
            home = MLB_TEAMS[pairs[i]]
            away = MLB_TEAMS[pairs[i + 1]]
            gid  = _game_id(d, home[1], away[1])
            dstr = d.isoformat()

            true_prob = np.random.uniform(0.50, 0.67)
            side      = "home" if true_prob > 0.5 else "away"
            fair_prob = true_prob - np.random.uniform(0.02, 0.04)
            edge      = true_prob - fair_prob
            if edge >= 0.03 and random.random() < 0.55:
                odds   = _american_odds(fair_prob)
                kelly  = round(edge * 0.25, 4)
                won    = random.random() < true_prob
                result = "WIN" if won else "LOSS"
                pnl    = round(kelly * _payout(odds), 4) if won else round(-kelly, 4)
                clv    = round(np.random.normal(0.008, 0.018), 4)
                team   = home[0] if side == "home" else away[0]
                ml_rows.append((
                    dstr, gid, home[0], away[0], side, team,
                    round(true_prob, 4), round(fair_prob, 4), round(edge, 4),
                    odds, kelly, result, pnl, clv,
                    datetime.now().isoformat()
                ))

            # totals
            total_line = round(np.random.uniform(7.5, 9.5), 1)
            pred_total = total_line + np.random.normal(0, 1.2)
            over_prob  = np.random.uniform(0.50, 0.63)
            tot_edge   = over_prob - np.random.uniform(0.44, 0.48)
            if tot_edge >= 0.04 and random.random() < 0.40:
                t_side = "over" if over_prob > 0.5 else "under"
                odds   = _american_odds(0.476)
                kelly  = round(tot_edge * 0.25, 4)
                won    = random.random() < over_prob
                result = "WIN" if won else "LOSS"
                pnl    = round(kelly * _payout(odds), 4) if won else round(-kelly, 4)
                clv    = round(np.random.normal(0.004, 0.012), 4)
                tot_rows.append((
                    dstr, gid, home[0], away[0], t_side,
                    round(total_line, 1), round(pred_total, 1),
                    round(over_prob, 4), round(tot_edge, 4),
                    odds, kelly, result, pnl, clv,
                    datetime.now().isoformat()
                ))

    conn.executemany(
        "INSERT INTO mlb_bet_log (predict_date,game_id,home_team,away_team,bet_side,bet_team,"
        "model_prob,fair_prob,edge,line,kelly_stake,result,profit_units,clv,recorded_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ml_rows
    )
    conn.executemany(
        "INSERT INTO mlb_totals_bet_log (predict_date,game_id,home_team,away_team,bet_side,"
        "total_line,pred_total,ou_prob,edge,line,kelly_stake,result,profit_units,clv,recorded_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", tot_rows
    )

    # Today's MLB predictions
    today_str  = today.isoformat()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mlb_predictions (
            game_id TEXT, predict_date TEXT,
            home_team TEXT, away_team TEXT, commence_time TEXT,
            home_pitcher TEXT, away_pitcher TEXT,
            home_era REAL, away_era REAL,
            model_home_prob REAL, model_away_prob REAL,
            home_fair_prob REAL, away_fair_prob REAL,
            home_edge REAL, away_edge REAL,
            home_value INTEGER, away_value INTEGER,
            home_kelly REAL, away_kelly REAL,
            home_price REAL, away_price REAL,
            bookmaker TEXT, actual_home_win INTEGER
        )
    """)
    conn.execute(f"DELETE FROM mlb_predictions WHERE predict_date='{today_str}'")

    mlb_today = [
        ("New York Yankees",    "Boston Red Sox",       "Gerrit Cole",       "Shane Bieber",   "19:05"),
        ("Los Angeles Dodgers", "Houston Astros",       "Clayton Kershaw",   "Justin Verlander","22:10"),
        ("Atlanta Braves",      "Chicago Cubs",         "Spencer Strider",   "Freddie Peralta","19:20"),
        ("San Diego Padres",    "Baltimore Orioles",    "Blake Snell",       "Zack Wheeler",   "21:40"),
        ("Texas Rangers",       "Cleveland Guardians",  "Max Scherzer",      "Logan Webb",     "20:05"),
    ]
    mlb_pred_rows = []
    for home_name, away_name, hpit, apit, tip in mlb_today:
        home_abbr = next(t[1] for t in MLB_TEAMS if t[0] == home_name)
        away_abbr = next(t[1] for t in MLB_TEAMS if t[0] == away_name)
        gid   = _game_id(today, home_abbr, away_abbr)
        ct    = f"{today_str}T{tip}:00Z"
        hp    = round(np.random.uniform(0.50, 0.63), 4)
        ap    = round(1 - hp, 4)
        hfair = round(hp - np.random.uniform(0.02, 0.04), 4)
        afair = round(1 - hfair, 4)
        hedge = round(hp - hfair, 4)
        aedge = round(ap - afair, 4)
        hval  = 1 if hedge >= 0.03 else 0
        aval  = 1 if aedge >= 0.03 else 0
        mlb_pred_rows.append((
            gid, today_str, home_name, away_name, ct,
            hpit, apit,
            round(np.random.uniform(3.1, 4.5), 2),
            round(np.random.uniform(3.1, 4.5), 2),
            hp, ap, hfair, afair, hedge, aedge,
            hval, aval,
            round(hedge * 0.25, 4) if hval else 0,
            round(aedge * 0.25, 4) if aval else 0,
            _american_odds(hfair), _american_odds(afair),
            "draftkings", None
        ))

    conn.executemany(
        "INSERT OR IGNORE INTO mlb_predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        mlb_pred_rows
    )
    conn.commit()


# ── Entry point ────────────────────────────────────────────────────────────────

def seed_if_empty():
    _rng()

    # NBA
    if not _is_seeded(DB_PATH, "bet_log", min_rows=10):
        conn = sqlite3.connect(DB_PATH)
        try:
            _seed_nba(conn)
        finally:
            conn.close()

    # MLB
    if not _is_seeded(MLB_DB, "mlb_bet_log", min_rows=10):
        conn = sqlite3.connect(MLB_DB)
        try:
            _seed_mlb(conn)
        finally:
            conn.close()


if __name__ == "__main__":
    seed_if_empty()
    print("Demo data seeded successfully.")
