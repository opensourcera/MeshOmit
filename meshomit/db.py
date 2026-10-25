# MeshOmit, Copyright (c) 2026 opensourcera. MIT License, see LICENSE.
"""SQLite storage for MeshOmit: conversation, bot replies, beacons, radio packets, repeater status."""
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    ts INTEGER NOT NULL,              -- unix time received / sent
    sender_ts INTEGER,                -- timestamp written by the sender
    channel_idx INTEGER,
    channel_name TEXT,
    sender TEXT,
    text TEXT,
    hops INTEGER,                     -- repeaters the packet went through (0 = direct)
    snr REAL,
    rssi REAL,
    path TEXT,                        -- comma separated hashes, best copy heard
    copies INTEGER DEFAULT 1,         -- how many copies arrived (via different repeaters)
    kind TEXT NOT NULL,               -- rx | backlog | beacon_reply | bot_reply | beacon | tx | dm | dm_tx
    is_trigger INTEGER DEFAULT 0,     -- 1 when the text is a test/ping the bot answers
    reply_to INTEGER,                 -- messages.id this answers (bot replies) / beacon id (beacon replies)
    beacon_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(ts);
CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender);

CREATE TABLE IF NOT EXISTS beacons (
    id INTEGER PRIMARY KEY,
    ts INTEGER NOT NULL,
    channel_idx INTEGER,
    text TEXT,
    replies INTEGER DEFAULT 0,
    message_id INTEGER
);

CREATE TABLE IF NOT EXISTS rx_packets (
    id INTEGER PRIMARY KEY,
    ts INTEGER NOT NULL,
    payload_type TEXT,
    route_type TEXT,
    snr REAL,
    rssi REAL,
    hash_size INTEGER,
    hops INTEGER,
    path TEXT,
    last_hop TEXT,                    -- hash of the repeater we heard it from ('' = direct)
    channel_name TEXT,
    sender_ts INTEGER,
    text TEXT
);
CREATE INDEX IF NOT EXISTS idx_rx_ts ON rx_packets(ts);
CREATE INDEX IF NOT EXISTS idx_rx_lasthop ON rx_packets(last_hop);

CREATE TABLE IF NOT EXISTS repeater_status (
    id INTEGER PRIMARY KEY,
    ts INTEGER NOT NULL,
    name TEXT,
    pubkey TEXT,
    ok INTEGER,                       -- 1 when login + status worked
    bat_mv INTEGER,
    uptime_s INTEGER,
    noise_floor INTEGER,
    last_rssi INTEGER,
    nb_recv INTEGER,
    nb_sent INTEGER,
    recv_errors INTEGER,
    airtime INTEGER,
    tx_queue INTEGER,
    sent_flood INTEGER,
    sent_direct INTEGER,
    recv_flood INTEGER,
    recv_direct INTEGER,
    trace_there REAL,                 -- SNR at the repeater of our trace
    trace_back REAL,                  -- SNR here of its answer
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_repstat_ts ON repeater_status(ts);

CREATE TABLE IF NOT EXISTS repeater_neighbors (
    id INTEGER PRIMARY KEY,
    ts INTEGER NOT NULL,
    repeater TEXT,
    neighbor TEXT,                    -- 8 hex chars as the repeater reports it
    neighbor_name TEXT,
    secs_ago INTEGER,
    snr REAL
);

CREATE TABLE IF NOT EXISTS reply_history (
    id INTEGER PRIMARY KEY,
    ts INTEGER NOT NULL,
    sender TEXT,
    template INTEGER                  -- index into the replies list
);
CREATE INDEX IF NOT EXISTS idx_replyhist_sender ON reply_history(sender);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    ts INTEGER NOT NULL,
    level TEXT,
    text TEXT
);
"""


class Db:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        # columns added after 1.0: an older database gets them here
        have = {d[1] for d in self.conn.execute("PRAGMA table_info(rx_packets)")}
        if "chan_hash" not in have:
            self.conn.execute("ALTER TABLE rx_packets ADD COLUMN chan_hash TEXT")  # 1-byte channel hash of group packets
        self.conn.commit()

    def close(self):
        self.closed = True
        self.conn.close()

    closed = False

    def _insert(self, table: str, row: dict) -> int:
        if self.closed:  # a last log line while the program shuts down
            return 0
        cols = ", ".join(row.keys())
        marks = ", ".join("?" for _ in row)
        cur = self.conn.execute("INSERT INTO %s (%s) VALUES (%s)" % (table, cols, marks), list(row.values()))
        self.conn.commit()
        return cur.lastrowid

    def add_message(self, **row) -> int:
        row.setdefault("ts", int(time.time()))
        return self._insert("messages", row)

    def add_beacon(self, channel_idx: int, text: str, message_id: int) -> int:
        return self._insert("beacons", {"ts": int(time.time()), "channel_idx": channel_idx, "text": text,
                                        "message_id": message_id})

    def count_beacon_reply(self, beacon_id: int):
        self.conn.execute("UPDATE beacons SET replies = replies + 1 WHERE id = ?", (beacon_id,))
        self.conn.commit()

    def add_rx_packet(self, **row) -> int:
        row.setdefault("ts", int(time.time()))
        return self._insert("rx_packets", row)

    def add_repeater_status(self, **row) -> int:
        row.setdefault("ts", int(time.time()))
        return self._insert("repeater_status", row)

    def add_neighbor(self, **row) -> int:
        row.setdefault("ts", int(time.time()))
        return self._insert("repeater_neighbors", row)

    def used_templates(self, sender: str) -> set:
        rows = self.conn.execute("SELECT template FROM reply_history WHERE sender = ?", (sender,)).fetchall()
        return {r[0] for r in rows}

    def add_reply_history(self, sender: str, template: int):
        self._insert("reply_history", {"ts": int(time.time()), "sender": sender, "template": template})

    def clear_reply_history(self, sender: str):
        self.conn.execute("DELETE FROM reply_history WHERE sender = ?", (sender,))
        self.conn.commit()

    def add_event(self, level: str, text: str):
        self._insert("events", {"ts": int(time.time()), "level": level, "text": text})

    # ---- stats for the screen ----
    def stats(self, since_ts: int) -> dict:
        q = self.conn.execute
        s = {}
        s["messages"] = q("SELECT COUNT(*) FROM messages WHERE ts >= ? AND kind IN ('rx','backlog')", (since_ts,)).fetchone()[0]
        s["triggers"] = q("SELECT COUNT(*) FROM messages WHERE ts >= ? AND is_trigger = 1", (since_ts,)).fetchone()[0]
        s["bot_replies"] = q("SELECT COUNT(*) FROM messages WHERE ts >= ? AND kind = 'bot_reply'", (since_ts,)).fetchone()[0]
        s["beacons"] = q("SELECT COUNT(*) FROM beacons WHERE ts >= ?", (since_ts,)).fetchone()[0]
        s["beacon_replies"] = q("SELECT COALESCE(SUM(replies),0) FROM beacons WHERE ts >= ?", (since_ts,)).fetchone()[0]
        s["senders"] = q("SELECT COUNT(DISTINCT sender) FROM messages WHERE ts >= ? AND kind IN ('rx','backlog')", (since_ts,)).fetchone()[0]
        return s

    def relay_counts(self, since_ts: int) -> dict:
        """Packets heard per last-hop repeater hash since since_ts."""
        rows = self.conn.execute(
            "SELECT last_hop, COUNT(*) FROM rx_packets WHERE ts >= ? GROUP BY last_hop", (since_ts,)).fetchall()
        return {h: n for h, n in rows}

    def unknown_channel_counts(self, since_ts: int) -> list:
        """(channel hash, packets, newest ts) of the group packets since since_ts that no channel could read."""
        return self.conn.execute(
            "SELECT chan_hash, COUNT(*), MAX(ts) FROM rx_packets WHERE ts >= ? AND payload_type = 'GRP_TXT' "
            "AND channel_name IS NULL AND chan_hash IS NOT NULL GROUP BY chan_hash", (since_ts,)).fetchall()

    def texts_since(self, since_ts: int) -> list:
        """The text of every message stored since since_ts."""
        return [r[0] for r in self.conn.execute(
            "SELECT text FROM messages WHERE ts >= ? AND text IS NOT NULL", (since_ts,))]

    def last_hop_stats(self, since_ts: int) -> list:
        """(last-hop hash, packets, best SNR, newest ts) per relaying repeater since since_ts; direct packets left out."""
        return self.conn.execute(
            "SELECT last_hop, COUNT(*), MAX(snr), MAX(ts) FROM rx_packets WHERE ts >= ? AND last_hop != '' "
            "GROUP BY last_hop", (since_ts,)).fetchall()

    def last_repeater_status(self, name: str):
        return self.conn.execute(
            "SELECT * FROM repeater_status WHERE name = ? ORDER BY ts DESC LIMIT 1", (name,)).fetchone()

    def last_repeater_row(self, name: str) -> dict | None:
        """The last poll of a repeater as a dict, or None."""
        cur = self.conn.execute("SELECT * FROM repeater_status WHERE name = ? ORDER BY ts DESC LIMIT 1", (name,))
        row = cur.fetchone()
        return dict(zip([d[0] for d in cur.description], row)) if row else None

    def battery_at(self, name: str, before_ts: int):
        """(ts, bat_mv) of the newest successful poll at or before before_ts, or None."""
        return self.conn.execute(
            "SELECT ts, bat_mv FROM repeater_status WHERE name = ? AND ok = 1 AND bat_mv IS NOT NULL AND ts <= ? "
            "ORDER BY ts DESC LIMIT 1", (name, before_ts)).fetchone()

    def battery_oldest_since(self, name: str, since_ts: int):
        """(ts, bat_mv) of the oldest successful poll after since_ts, or None."""
        return self.conn.execute(
            "SELECT ts, bat_mv FROM repeater_status WHERE name = ? AND ok = 1 AND bat_mv IS NOT NULL AND ts >= ? "
            "ORDER BY ts ASC LIMIT 1", (name, since_ts)).fetchone()

    def latest_neighbors(self, name: str) -> list:
        """(neighbor hash, name, secs_ago, snr) from the newest poll of this repeater that reported neighbours."""
        last = self.conn.execute("SELECT MAX(ts) FROM repeater_neighbors WHERE repeater = ?", (name,)).fetchone()[0]
        if last is None:
            return []
        return self.conn.execute(
            "SELECT neighbor, neighbor_name, secs_ago, snr FROM repeater_neighbors WHERE repeater = ? AND ts >= ? "
            "ORDER BY snr DESC", (name, last - 60)).fetchall()

    # ---- dashboard ----
    def hourly(self, hours: int = 24) -> dict:
        """Per-hour counts for the last `hours` hours, oldest first: messages heard, tests heard, replies sent,
        beacon replies received. Each list has exactly `hours` entries."""
        now = int(time.time())
        start = now - hours * 3600
        out = {"messages": [0] * hours, "triggers": [0] * hours, "replies": [0] * hours,
               "beacon_replies": [0] * hours, "stations": [0] * hours}
        rows = self.conn.execute(
            "SELECT ts, kind, is_trigger, sender FROM messages WHERE ts >= ?", (start,)).fetchall()
        seen: dict[int, set] = {}
        for ts, kind, trig, sender in rows:
            i = min(hours - 1, max(0, (ts - start) // 3600))
            if kind in ("rx", "backlog", "beacon_reply"):
                out["messages"][i] += 1
                seen.setdefault(i, set()).add(sender)
            if trig:
                out["triggers"][i] += 1
            if kind == "bot_reply":
                out["replies"][i] += 1
            if kind == "beacon_reply":
                out["beacon_replies"][i] += 1
        for i, names in seen.items():
            out["stations"][i] = len(names)
        return out

    def top_senders(self, since_ts: int, n: int = 12):
        """Stations heard most: name, messages, fewest hops, best SNR, last heard."""
        return self.conn.execute(
            "SELECT sender, COUNT(*) AS c, MIN(hops), MAX(snr), MAX(ts) FROM messages "
            "WHERE ts >= ? AND kind IN ('rx','backlog','beacon_reply') AND sender != '' "
            "GROUP BY sender ORDER BY c DESC LIMIT ?", (since_ts, n)).fetchall()

    def beacon_history(self, n: int = 12):
        return self.conn.execute(
            "SELECT ts, text, replies FROM beacons ORDER BY ts DESC LIMIT ?", (n,)).fetchall()

    def beacon_summary(self, since_ts: int):
        return self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(replies),0), COALESCE(SUM(replies > 0),0) FROM beacons WHERE ts >= ?",
            (since_ts,)).fetchone()

    def repeater_history(self, name: str, n: int = 48):
        """Oldest first: ts, bat_mv, noise_floor, trace_there, trace_back, ok."""
        rows = self.conn.execute(
            "SELECT ts, bat_mv, noise_floor, trace_there, trace_back, ok FROM repeater_status WHERE name = ? "
            "ORDER BY ts DESC LIMIT ?", (name, n)).fetchall()
        return rows[::-1]

    def repeater_names(self):
        return [r[0] for r in self.conn.execute("SELECT DISTINCT name FROM repeater_status ORDER BY name")]

    def hops_histogram(self, since_ts: int) -> dict:
        rows = self.conn.execute(
            "SELECT hops, COUNT(*) FROM messages WHERE ts >= ? AND kind IN ('rx','beacon_reply') AND hops IS NOT NULL "
            "GROUP BY hops ORDER BY hops", (since_ts,)).fetchall()
        return {h: n for h, n in rows}

    def recent_replies(self, n: int = 8):
        """Our last replies with what they answered: ts, to whom, our text."""
        return self.conn.execute(
            "SELECT m.ts, r.sender, m.text FROM messages m LEFT JOIN messages r ON r.id = m.reply_to "
            "WHERE m.kind = 'bot_reply' ORDER BY m.ts DESC LIMIT ?", (n,)).fetchall()
