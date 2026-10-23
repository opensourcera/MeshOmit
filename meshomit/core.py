# MeshOmit, Copyright (c) 2026 opensourcera. MIT License, see LICENSE.
"""MeshOmit engine: link to the node (Bluetooth, serial or TCP), listening, test-reply bot, beacons, repeater polling.
The engine knows nothing about the screen; it reports through a Ui object with these methods:
    event(text, level)          progress and problems
    message(rec)                a conversation line (dict with ts, channel, sender, text, kind, hops, snr, rssi, path)
    status(dict)                connection and counters
    repeaters(list_of_dict)     latest repeater readings
"""
import asyncio
import json
import os
import random
import re
import sys
import time
from collections import deque

from meshcore import EventType

from . import connection
from .db import Db


DEFAULT_MESSAGES = {
    "replies": [
        "@[{name}] hi, im in {location}, you?",
        "@[{name}] hey, {hops} here in {location}",
        "@[{name}] hearing you ok, {hops}. how about you?",
        "@[{name}] hi from {location}, what radio you got?",
        "@[{name}] got you at {snr} db, nice",
        "@[{name}] hello, {location} here, you?",
        "@[{name}] copy, {hops}",
        "@[{name}] first time hearing you, where are you?",
    ],
    "brb": ["brb", "brb..", "back in a bit", "1 min, brb", "brb, call"],
    "beacons": [
        "{greeting} from {location}, anyone around?",
        "hi all, {me} in {location}, who hears me?",
        "{location} here, how is the mesh your side?",
        "anyone out there? {location} calling",
        "quiet here in {location}.. anyone?",
    ],
    "mentions": [
        "@[{name}] hi, yes im here in {location}",
        "@[{name}] hearing you {hops}, {location}",
        "@[{name}] hey, got you here in {location}",
    ],
    "operator_replies": [
        "@[{name}] got you {hops} {via} here in {location}, {snr} dB",
        "@[{name}] copy, {hops} {via}, {location}",
    ],
    "quick": [
        "Test",
        "hi all, anyone around?",
        "copy, thanks",
        "73",
        "good copy here, how do you hear me?",
        "who is on tonight?",
    ],
    "emoticons": [":)", ";)", ":D", ":P", ":(", "<3", "o/", "^^", "73", "+1"],
}


def load_messages(cfg: dict, cfg_path: str | None) -> dict:
    """The text lists: messages.json next to the config (or cfg["messages_file"]), else the lists that may
    still sit in config.json (older layout), else the built-in defaults."""
    msgs = {k: list(v) for k, v in DEFAULT_MESSAGES.items()}
    for k, src in (("replies", cfg.get("bot", {}).get("replies")), ("brb", cfg.get("bot", {}).get("brb")),
                   ("beacons", cfg.get("beacon", {}).get("messages"))):
        if src:
            msgs[k] = list(src)
    path = cfg.get("messages_file", "messages.json")
    if cfg_path and not os.path.isabs(path):
        path = os.path.join(os.path.dirname(os.path.abspath(cfg_path)), path)
    if not os.path.exists(path) and getattr(sys, "_MEIPASS", None):  # MeshOmit.exe ships a copy
        alt = os.path.join(sys._MEIPASS, "messages.json")
        if os.path.exists(alt):
            path = alt
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        for k in msgs:
            if isinstance(data.get(k), list) and data[k]:
                msgs[k] = [str(x) for x in data[k]]
    msgs["_path"] = path
    return msgs


def read_password(path: str, key: str | None) -> str:
    text = open(path, encoding="utf-8").read()
    if key:
        m = re.search(r"%s\s*=\s*(\S+)" % re.escape(key), text)
        if not m:
            raise ValueError("no '%s=' line in %s" % (key, path))
        return m.group(1)
    return text.strip()


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, str]:
    """Great-circle distance in km and a compass direction (N, NE, ...) from point 1 to point 2."""
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    km = 2 * 6371.0 * math.asin(math.sqrt(a))
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    brg = (math.degrees(math.atan2(y, x)) + 360) % 360
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return km, names[int((brg + 22.5) // 45) % 8]


class Engine:
    def __init__(self, cfg: dict, db: Db, ui, cfg_path: str | None = None):
        self.cfg = cfg
        self.db = db
        self.ui = ui
        self.mc = None
        self.conn_cfg = cfg.get("connection") or {"type": "ble", "address": cfg.get("device", {}).get("address")}
        self.pin = self.conn_cfg.get("pin") or cfg.get("pin")
        self.node_name = cfg.get("node_name") or cfg.get("device", {}).get("name") or "?"
        self.msgs = load_messages(cfg, cfg_path)
        self.started = int(time.time())
        self.connected_at = None
        self.stop_event = asyncio.Event()
        self.cmd_lock = asyncio.Lock()
        self.bot_paused = False
        # starts as a plain chat client; "bot" (answers and beacons) is switched on with the m key
        self.mode = cfg.get("start_mode", "operator")
        self.contacts_loaded = False
        self.on_channels_changed = None  # callback(channels dict) set by the screen
        self.rooms: dict = dict(cfg.get("rooms") or {})  # name -> {"creator", "secret" (hex or None), "ts"}
        self.pending_invite = None  # {"name", "secret", "from"} from the last invite DM
        try:
            self.channels = {int(k): v for k, v in cfg.get("channels", {"0": "Public", "1": "#test"}).items()}
        except (TypeError, ValueError):
            raise ValueError("config.json: the keys of \"channels\" must be the slot numbers 0 to 7, as strings")
        self.known = {k.lower(): v for k, v in cfg.get("known_prefixes", {}).items()}
        for r in cfg.get("repeaters", []):
            self.known[r["pubkey"][:4].lower()] = r["name"]
            self.known[r["pubkey"][:2].lower()] = r["name"]
        # bot state
        bot = cfg.get("bot", {})
        self.bot_enabled = bool(bot.get("enabled", True))
        self.triggers = [str(t).lower() for t in bot.get("triggers", ["test", "ping", "radio check"])]
        try:
            self.reply_channels = set(int(c) for c in bot.get("reply_channels", [1]))
        except (TypeError, ValueError):
            raise ValueError("config.json: bot.reply_channels must be a list of channel numbers")
        self.per_sender_s = int(bot.get("per_sender_minutes", 10)) * 60
        self.max_per_hour = int(bot.get("max_per_hour", 6))
        d = bot.get("delay_s", [2, 6])
        self.delay_range = [float(d), float(d)] if isinstance(d, (int, float)) else [float(d[0]), float(d[-1])]
        self.ignore_senders = [s.lower() for s in bot.get("ignore_senders_containing", ["bot"])]
        self.answer_mentions = bool(bot.get("answer_mentions", False))
        self.last_reply_to: dict[str, float] = {}
        self.reply_times: deque = deque()
        # beacon state
        self.beacon_cfg = cfg.get("beacon", {})
        self.beacon_idx = -1
        self.current_beacon = None  # (beacon_id, ts)
        self.next_beacon_at = None
        self.next_poll_at = None
        # recent raw packets, used to attach SNR/RSSI/path to channel messages
        self.recent_rx: deque = deque(maxlen=200)
        self.repeater_rows: dict[str, dict] = {}
        self.counters = {"messages": 0, "triggers": 0, "replies": 0, "beacons": 0, "beacon_replies": 0}
        self.pin_needed = asyncio.Event()
        self.pending_cli: dict[str, list] = {}
        self.tasks: set = set()

    # ------------------------------------------------------------------ helpers
    def log(self, text: str, level: str = "info"):
        self.db.add_event(level, text)
        self.ui.event(text, level)

    def hop_name(self, h: str) -> str:
        return self.known.get(h.lower(), h)

    @staticmethod
    def split_path(path: str, hash_size: int) -> list[str]:
        """The hop hashes of a path: either already comma separated (our rx log form) or a plain hex
        string of fixed-width hashes from the node."""
        if "," in path:
            return [h for h in path.split(",") if h]
        step = 2 * max(1, hash_size)
        return [path[i:i + step] for i in range(0, len(path), step)]

    def path_names(self, path: str, hash_size: int) -> list[str]:
        return [self.hop_name(h) for h in self.split_path(path, hash_size)]

    def spawn(self, coro) -> asyncio.Task:
        """create_task with a reference kept, so a reply waiting out its delay is never garbage collected."""
        t = asyncio.create_task(coro)
        self.tasks.add(t)
        t.add_done_callback(self.tasks.discard)
        return t

    def is_trigger(self, text: str) -> bool:
        t = text.strip().lower().rstrip("!?. ")
        return t in self.triggers

    @staticmethod
    def split_sender(text: str) -> tuple[str, str]:
        if ": " in text:
            a, b = text.split(": ", 1)
            return a.strip(), b
        return "", text

    # ------------------------------------------------------------------ connection
    async def run(self):
        self.log("Bot started", "ok")
        self.ui.status(self.status_dict("starting"))
        while not self.stop_event.is_set():
            try:
                await self.connect_and_serve()
            except connection.PairingError as e:
                self.log("Pairing: %s" % e, "warn")
                self.pin = None
                self.ui.status(self.status_dict("need PIN"))
                self.pin_needed.set()
                await self.wait_for_pin()
            except Exception as e:
                self.log("Link lost: %s" % e, "warn")
                self.ui.status(self.status_dict("reconnecting"))
                await self.sleep(10)
        self.log("Bot stopped", "info")

    async def wait_for_pin(self):
        while not self.stop_event.is_set() and not self.pin:
            await asyncio.sleep(0.5)
        self.pin_needed.clear()

    async def sleep(self, seconds: float):
        try:
            await asyncio.wait_for(self.stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    def link_label(self) -> str:
        c = self.conn_cfg
        kind = (c.get("type") or "ble").lower()
        if kind == "serial":
            return "serial %s" % c.get("port")
        if kind == "tcp":
            return "tcp %s:%s" % (c.get("host"), c.get("port", 5000))
        return "Bluetooth %s" % c.get("address")

    async def connect_and_serve(self):
        self.ui.status(self.status_dict("connecting"))
        self.log("Connecting to %s..." % self.link_label())
        self.mc = await connection.connect(self.conn_cfg, self.pin, lambda t: self.log(t))
        info = self.mc.self_info or {}
        self.node_name = info.get("name") or self.node_name
        self.connected_at = int(time.time())
        self.log("Connected: %s" % self.node_name, "ok")
        await self.setup()
        self.ui.status(self.status_dict("listening"))
        self.log("Listening on " + ", ".join(self.channels.values()), "ok")
        tasks = [asyncio.create_task(self.beacon_loop()), asyncio.create_task(self.repeater_loop()),
                 asyncio.create_task(self.status_loop()), asyncio.create_task(self.load_contacts()),
                 asyncio.create_task(self.pull_loop())]
        try:
            while not self.stop_event.is_set():
                await asyncio.sleep(2)
                if not connection.is_alive(self.mc):
                    raise ConnectionError("link dropped")
        finally:
            for t in tasks:
                t.cancel()
            try:
                await self.mc.stop_auto_message_fetching()
            except Exception:
                pass
            try:
                await self.mc.disconnect()
            except Exception:
                pass
            self.mc = None
            self.connected_at = None

    async def pull_loop(self):
        """Ask the node for queued messages every 20 s. The library fetches them when the node pushes a
        "messages waiting" notice, but that push can be missed right after connecting, after which nothing
        would ever arrive although the node decrypts everything; this pulls whatever is queued anyway."""
        while self.mc:
            await asyncio.sleep(20)
            n = 0
            async with self.cmd_lock:
                for _ in range(32):
                    try:
                        r = await self.mc.commands.get_msg(timeout=5)
                    except Exception:
                        break
                    if r is None or r.type.name in ("NO_MORE_MSGS", "ERROR"):
                        break
                    n += 1
                    await asyncio.sleep(0.1)
            if n:
                self.log("Pulled %d queued message%s the node had not pushed" % (n, "" if n == 1 else "s"))

    async def setup(self):
        mc = self.mc
        # clock: repeaters drop logins with a stale timestamp
        r = await mc.commands.get_time()
        dev = (r.payload or {}).get("time") if r else None
        now = int(time.time())
        if dev is None or abs(dev - now) > 30:
            await mc.commands.set_time(now)
            self.log("Clock set (device was off by %s s)" % (None if dev is None else dev - now))
        # channels: registers the keys so raw packets can be matched to messages
        for idx in self.channels:
            r = await mc.commands.get_channel(idx)
            name = (r.payload or {}).get("channel_name") if r else None
            if name:
                self.channels[idx] = name
        mc.set_decrypt_channel_logs(True)
        mc.subscribe(EventType.RX_LOG_DATA, self.on_rx_log)
        mc.subscribe(EventType.CHANNEL_MSG_RECV, self.on_channel_msg)
        mc.subscribe(EventType.CONTACT_MSG_RECV, self.on_contact_msg)
        await mc.start_auto_message_fetching()

    def status_dict(self, state: str) -> dict:
        now = time.time()
        return {
            "state": state, "node": self.node_name, "address": self.link_label(),
            "since": self.connected_at, "started": self.started,
            "next_beacon": self.next_beacon_at, "next_poll": self.next_poll_at,
            "bot_paused": self.bot_paused, "mode": self.mode, "counters": dict(self.counters),
            "contacts": len(self.mc.contacts) if self.mc else 0,
            "relays_1h": self.db.relay_counts(int(now) - 3600),
        }

    async def status_loop(self):
        while True:
            self.ui.status(self.status_dict("listening"))
            await asyncio.sleep(5)

    # ------------------------------------------------------------------ receiving
    def on_rx_log(self, e):
        p = e.payload or {}
        path = p.get("path") or ""
        sz = p.get("path_hash_size") or 1
        step = 2 * sz
        hops = [path[i:i + step] for i in range(0, len(path), step)]
        rec = {
            "ts": int(time.time()), "payload_type": p.get("payload_typename"), "route_type": p.get("route_typename"),
            "snr": p.get("snr"), "rssi": p.get("rssi"), "hash_size": sz, "hops": len(hops), "path": ",".join(hops),
            "last_hop": hops[-1] if hops else "", "channel_name": p.get("chan_name"),
            "sender_ts": p.get("sender_timestamp"), "text": p.get("message"),
        }
        self.recent_rx.append(rec)
        self.db.add_rx_packet(**rec)

    def best_copy(self, sender_ts, text):
        """Among the copies of one channel message heard in the last seconds, the strongest."""
        best = None
        n = 0
        for r in self.recent_rx:
            if r["sender_ts"] == sender_ts and r["text"] == text:
                n += 1
                if best is None or (r["snr"] or -99) > (best["snr"] or -99):
                    best = r
        return best, n

    def on_channel_msg(self, e):
        p = e.payload or {}
        idx = p.get("channel_idx")
        text = p.get("text") or ""
        sender, body = self.split_sender(text)
        sender_ts = p.get("sender_timestamp")
        now = int(time.time())
        age = now - sender_ts if sender_ts else 0
        backlog = age > 120 or age < -120
        copy, copies = self.best_copy(sender_ts, text)
        hops = p.get("path_len")
        if hops is not None and hops >= 64:
            hops = None
        snr = copy["snr"] if copy else p.get("SNR")
        rssi = copy["rssi"] if copy else p.get("RSSI")
        hash_size = copy["hash_size"] if copy else 1
        if copy:
            path, hops = copy["path"], copy["hops"]
        else:
            path = ",".join(self.split_path(p.get("path") or "", hash_size))
        mine = sender == self.node_name
        trigger = (not mine) and self.is_trigger(body) and idx in self.reply_channels
        mentioned = (not mine) and not trigger and idx in self.reply_channels and self.answer_mentions \
            and ("@[%s]" % self.node_name).lower() in body.lower()
        rec = {
            "ts": now, "sender_ts": sender_ts, "channel_idx": idx, "channel_name": self.channels.get(idx, str(idx)),
            "sender": sender, "text": body, "hops": hops, "snr": snr, "rssi": rssi, "path": path, "copies": copies,
            "kind": "backlog" if backlog else "rx", "is_trigger": 1 if trigger else 0,
        }
        # beacon replies: anything naming us on the beacon channel inside the reply window
        beacon_id = None
        if self.current_beacon and not mine and not backlog:
            b_id, b_ts = self.current_beacon
            window = int(self.beacon_cfg.get("reply_window_minutes", 10)) * 60
            if now - b_ts <= window and self.node_name.lower() in body.lower():
                beacon_id = b_id
                self.db.count_beacon_reply(b_id)
                self.counters["beacon_replies"] += 1
                rec["kind"] = "beacon_reply"
        rec["beacon_id"] = beacon_id
        msg_id = self.db.add_message(**rec)
        rec["id"] = msg_id
        rec["path_names"] = self.path_names(path, hash_size) if path else []
        if not backlog:
            self.counters["messages"] += 1
        self.ui.message(rec)
        if trigger and not backlog:
            self.counters["triggers"] += 1
            self.spawn(self.maybe_reply(rec))
        elif mentioned and not backlog:
            self.spawn(self.maybe_reply(rec, "mentions"))

    def on_contact_msg(self, e):
        p = e.payload or {}
        full_prefix = (p.get("pubkey_prefix") or "").lower()
        prefix = full_prefix[:4]
        if prefix in self.pending_cli:  # an answer to a repeater CLI command we are waiting for
            self.pending_cli[prefix].append(p.get("text") or "")
            return
        name, key = self.contact_by_prefix(full_prefix)
        now = int(time.time())
        sender_ts = p.get("sender_timestamp")
        hops = p.get("path_len")
        if hops is None or hops < 0 or hops >= 64:  # 255 means "no path information"
            hops = None
        rec = {"ts": now, "sender_ts": sender_ts, "channel_idx": None, "channel_name": "DM",
               "sender": name or full_prefix[:8], "text": p.get("text") or "", "hops": hops, "snr": p.get("SNR"),
               "rssi": None, "path": "", "copies": 1, "kind": "dm", "is_trigger": 0, "dm_key": key}
        rec["id"] = self.db.add_message(**{k: v for k, v in rec.items() if k not in ("dm_key",)})
        rec["path_names"] = []
        self.counters["messages"] += 1
        m = re.search(r"join me on channel (\S+?)(?:,| |$)(?:.*?key ([0-9a-fA-F]{32}))?", rec["text"])
        if m:
            secret = bytes.fromhex(m.group(2)) if m.group(2) else None
            self.pending_invite = {"name": m.group(1).rstrip(",.)"), "secret": secret, "from": rec["sender"]}
            self.log("%s invites you to %s (press j to join)" % (rec["sender"], self.pending_invite["name"]), "ok")
        self.ui.message(rec)

    # ------------------------------------------------------------------ contacts, DMs, rooms
    async def load_contacts(self):
        """Fetch the node's contact list once (slow over Bluetooth with many contacts) so DMs show names
        and the operator can pick people by name."""
        await asyncio.sleep(3)
        for attempt in range(3):
            if not self.mc:
                return
            async with self.cmd_lock:
                try:
                    # a fresh app start first: the fetch right after connecting returns nothing on the
                    # Cardputer, the same fetch after a second app start streams the whole list
                    await self.mc.commands.send_appstart(timeout=5)
                    r = await self.mc.commands.get_contacts(timeout=20)
                    why = ""
                    if r is not None and r.type.name != "CONTACTS":
                        why = "%s %s" % (r.type.name, (r.payload or {}).get("reason") or (r.payload or {}).get("error") or "")
                except Exception as e:
                    why = str(e)
            n = len(self.mc.contacts)
            if n:
                self.contacts_loaded = True
                self.log("Contacts: %d known to the node" % n, "ok")
                return
            self.log("Contacts: none received (%s), try %d/3" % (why.strip() or "empty list", attempt + 1), "warn")
            await asyncio.sleep(30)

    def contact_by_prefix(self, prefix: str) -> tuple[str, str]:
        """(name, public key) of the contact whose key starts with prefix, or ('', '')."""
        if not self.mc or not prefix:
            return "", ""
        for key, c in self.mc.contacts.items():
            if key.lower().startswith(prefix):
                return c.get("adv_name") or key[:8], key
        return "", ""

    CONTACT_TYPES = {1: "companion", 2: "repeater", 3: "room server", 4: "sensor"}

    def contact_info(self, name: str) -> dict | None:
        """What the node's contact list knows about a name: key, type, last advert, position and, when our
        own node has a position, distance and direction. Exact name first, then a part of the name."""
        if not self.mc:
            return None
        want = name.lower().strip()
        hits = [(k, c) for k, c in self.mc.contacts.items() if (c.get("adv_name") or "").lower() == want]
        if not hits:
            hits = [(k, c) for k, c in self.mc.contacts.items() if want in (c.get("adv_name") or "").lower()]
        if not hits:
            return None
        hits.sort(key=lambda kc: -(kc[1].get("last_advert") or 0))
        k, c = hits[0]
        lat, lon = c.get("adv_lat") or 0.0, c.get("adv_lon") or 0.0
        has_pos = bool(lat or lon)
        info = {"name": c.get("adv_name") or k[:8], "key": k, "last_advert": c.get("last_advert") or 0,
                "type": self.CONTACT_TYPES.get(c.get("type"), "node"), "path_len": c.get("out_path_len"),
                "lat": lat if has_pos else None, "lon": lon if has_pos else None, "km": None, "dir": None}
        me = self.mc.self_info or {}
        mlat, mlon = me.get("adv_lat") or 0.0, me.get("adv_lon") or 0.0
        if has_pos and (mlat or mlon):
            info["km"], info["dir"] = distance_km(mlat, mlon, lat, lon)
        return info

    def find_contacts(self, query: str, limit: int = 12) -> list[tuple[str, str]]:
        """(name, key) of contacts whose name contains query, most recently heard first."""
        if not self.mc:
            return []
        q = query.lower().strip()
        rows = [(c.get("adv_name") or key[:8], key, c.get("last_advert") or 0)
                for key, c in self.mc.contacts.items() if (not q) or q in (c.get("adv_name") or "").lower()]
        rows.sort(key=lambda r: -r[2])
        return [(n, k) for n, k, _ in rows[:limit]]

    async def send_dm(self, key: str, name: str, text: str) -> bool:
        if not self.mc:
            return False
        async with self.cmd_lock:
            try:
                r = await self.mc.commands.send_msg(key, text)
                ok = bool(r) and r.type.name != "ERROR"
            except Exception as e:
                self.log("DM failed: %s" % e, "warn")
                ok = False
        rec = {"ts": int(time.time()), "channel_idx": None, "channel_name": "DM", "sender": self.node_name,
               "text": text, "kind": "dm_tx", "reply_to": None, "beacon_id": None}
        rec["id"] = self.db.add_message(**rec)
        rec["path_names"] = []
        rec["to"] = name
        rec["dm_key"] = key
        self.ui.message(rec)
        if not ok:
            self.log("Device refused the DM to %s" % name, "warn")
        return ok

    async def add_room(self, name: str, secret: bytes | None, creator: str | None = None) -> tuple[int | None, str]:
        """Create or join a channel on the node. A name starting with # is a hashtag room: everyone who adds
        a channel with that exact name gets the same key. With a 16-byte secret it is a private room.
        Returns (channel index, message)."""
        if not self.mc:
            return None, "not connected"
        name = name.strip()
        if not name:
            return None, "give the room a name"
        if secret is None and not name.startswith("#"):
            name = "#" + name
        for idx, n in self.channels.items():
            if n == name:
                return idx, "already on %s" % name
        async with self.cmd_lock:
            idx = None
            for cand in range(0, 8):
                if cand in self.channels:
                    continue
                r = await self.mc.commands.get_channel(cand)
                existing = (r.payload or {}).get("channel_name") if r else None
                if existing:
                    self.channels[cand] = existing  # the node already had it, keep listening to it too
                    if existing == name:
                        idx = cand
                        break
                    continue
                idx = cand
                break
            if idx is None:
                return None, "no free channel slot on the node (8 max)"
            if self.channels.get(idx) != name:
                r = await self.mc.commands.set_channel(idx, name, secret)
                if not r or r.type.name == "ERROR":
                    return None, "node refused the channel"
                await self.mc.commands.get_channel(idx)  # registers the key for decoding
            self.channels[idx] = name
        self.rooms[name] = {"creator": creator or self.node_name, "secret": secret.hex() if secret else None,
                            "ts": int(time.time())}
        self.log("Room %s on channel %d" % (name, idx), "ok")
        if self.on_channels_changed:
            self.on_channels_changed(dict(self.channels))
        return idx, "joined %s (channel %d)" % (name, idx)

    @staticmethod
    def invite_text(name: str, secret: bytes | None) -> str:
        if secret is None:
            return "join me on channel %s (add it as a channel with that exact name)" % name
        return "join me on channel %s, key %s" % (name, secret.hex())

    # ------------------------------------------------------------------ the bot
    async def maybe_reply(self, rec: dict, which: str = "replies"):
        if not self.bot_enabled:
            return
        if self.bot_paused or self.mode != "bot":
            self.log("Bot %s, not answering %s" % ("paused" if self.bot_paused else "in operator mode", rec["sender"]),
                     "info")
            return
        sender = rec["sender"]
        low = sender.lower()
        if not sender or any(s in low for s in self.ignore_senders):
            return
        now = time.time()
        if now - self.last_reply_to.get(sender, 0) < self.per_sender_s:
            self.log("Not answering %s again yet" % sender, "info")
            return
        while self.reply_times and now - self.reply_times[0] > 3600:
            self.reply_times.popleft()
        if len(self.reply_times) >= self.max_per_hour:
            self.log("Hourly reply limit reached, staying quiet", "warn")
            return
        delay = random.uniform(self.delay_range[0], self.delay_range[1])
        await asyncio.sleep(delay)
        text = self.build_reply(rec, which)
        ok = await self.send_channel(rec["channel_idx"], text, kind="bot_reply", reply_to=rec["id"])
        if ok:
            self.last_reply_to[sender] = time.time()
            self.reply_times.append(time.time())
            self.counters["replies"] += 1

    @staticmethod
    def hops_words(hops) -> str:
        if hops is None:
            return "a few hops"
        if hops == 0:
            return "direct, no repeater"
        return "%d hop%s" % (hops, "" if hops == 1 else "s")

    @staticmethod
    def daypart() -> str:
        h = time.localtime().tm_hour
        return "morning" if 5 <= h < 12 else "afternoon" if 12 <= h < 17 else "evening" if 17 <= h < 22 else "night"  # not used in the default texts

    SLANG = [("you are", "u r"), ("you", "u"), ("your", "ur"), ("are", "r"), ("good night", "gud nite"),
             ("good", "gud"), ("night", "nite"), ("thanks", "thx"), ("please", "pls"), ("to", "2"), ("for", "4"),
             ("people", "ppl"), ("about", "abt"), ("okay", "ok"), ("because", "cuz"), ("tonight", "2nite")]
    KEYS = "qwertyuiopasdfghjklzxcvbnm"
    NEIGHBOURS = {"a": "sq", "s": "ad", "d": "sf", "f": "dg", "g": "fh", "h": "gj", "j": "hk", "k": "jl", "l": "k",
                  "q": "wa", "w": "qe", "e": "wr", "r": "et", "t": "ry", "y": "tu", "u": "yi", "i": "uo", "o": "ip",
                  "p": "o", "z": "x", "x": "zc", "c": "xv", "v": "cb", "b": "vn", "n": "bm", "m": "n"}

    def humanize(self, text: str) -> str:
        """Shorten like a person typing on a small keyboard, with the odd slip. The @[name] mention and numbers
        are left alone so the message still reaches the right person and keeps its facts."""
        hc = self.cfg.get("human", {})
        slang_chance = float(hc.get("slang_chance", 0.7))
        typo_chance = float(hc.get("typo_chance", 0.35))
        mention = ""
        body = text
        if text.startswith("@[") and "] " in text:
            mention, body = text.split("] ", 1)
            mention += "] "
        # slang, word by word so "to" inside "tomorrow" is not touched
        words = body.split(" ")
        out = []
        for w in words:
            core_w = w.strip(".,!?")
            low = core_w.lower()
            repl = None
            for a, b in self.SLANG:
                if " " in a:
                    continue
                if low == a and random.random() < slang_chance:
                    repl = b
                    break
            if repl is not None:
                w = w.replace(core_w, repl)
            out.append(w)
        body = " ".join(out)
        for a, b in self.SLANG:  # two-word ones
            if " " in a and a in body.lower() and random.random() < slang_chance:
                i = body.lower().index(a)
                body = body[:i] + b + body[i + len(a):]
        # one typo in one word, never in numbers
        if random.random() < typo_chance:
            keep = {"hops", "hop", "direct", "repeater", "snr", "rssi"}  # the facts stay readable
            idxs = [i for i, w in enumerate(out) if len(w.strip(".,!?")) >= 4 and w.strip(".,!?").isalpha()
                    and w.strip(".,!?").lower() not in keep]
            words = body.split(" ")
            idxs = [i for i in idxs if i < len(words)]
            if idxs:
                i = random.choice(idxs)
                w = words[i]
                k = random.randrange(1, len(w.strip(".,!?")))
                ch = w[k].lower()
                kind = random.random()
                if kind < 0.5:                      # doubled letter: "hearring"
                    w = w[:k] + w[k] + w[k:]
                elif kind < 0.8 and ch in self.NEIGHBOURS:  # neighbouring key: "hesring"
                    w = w[:k] + random.choice(self.NEIGHBOURS[ch]) + w[k + 1:]
                else:                               # swapped letters: "haering"
                    if k + 1 < len(w) and w[k + 1].isalpha():
                        w = w[:k] + w[k + 1] + w[k] + w[k + 2:]
                words[i] = w
                body = " ".join(words)
        # people rarely bother with the final full stop or a capital
        body = body.rstrip(".")
        if random.random() < 0.5 and body[:1].isupper() and not body[:2].isupper():
            body = body[0].lower() + body[1:]
        return mention + body

    def place(self) -> str:
        """One of the configured names for where we are, chosen at random each time."""
        names = self.cfg.get("locations") or [self.cfg.get("location", "here")]
        return random.choice(names)

    def greeting(self) -> str:
        """Time-free greeting: the clock here says nothing about where the other person is."""
        return random.choice(["hello", "hi", "hey", "hi there", "howdy"])

    def build_reply(self, rec: dict, which: str = "replies") -> str:
        """Pick a line this sender has not had yet (random among the unused ones), fill in the blanks.
        which = "replies" for test answers, "mentions" for answers to people who name us."""
        templates = self.msgs.get(which) or self.msgs["replies"]
        sender = rec["sender"]
        hist_key = sender if which == "replies" else "%s|%s" % (which, sender)
        # now and then a person just says they will be back, instead of answering
        brb = self.msgs["brb"]
        if which == "replies" and random.random() < float(self.cfg.get("bot", {}).get("brb_chance", 0.15)):
            return "@[%s] %s" % (sender, random.choice(brb))
        used = self.db.used_templates(hist_key)
        candidates = [i for i in range(len(templates)) if i not in used]
        if not candidates:  # this sender has had them all: start over
            self.db.clear_reply_history(hist_key)
            candidates = list(range(len(templates)))
        snr = rec.get("snr")
        if snr is None:  # lines that quote the SNR need one
            candidates = [i for i in candidates if "{snr}" not in templates[i]] or candidates
        idx = random.choice(candidates)
        self.db.add_reply_history(hist_key, idx)
        path = rec.get("path_names") or []
        try:
            text = templates[idx].format(
                name=sender, location=self.place(), hops=self.hops_words(rec.get("hops")),
                snr="?" if snr is None else "%.1f" % snr,
                rssi="?" if rec.get("rssi") is None else "%.0f" % rec["rssi"],
                path=",".join(path) if path else "?", daypart=self.daypart(), greeting=self.greeting(),
                me=self.node_name)
        except (KeyError, IndexError, ValueError) as e:
            self.log("messages.json: bad placeholder in %s line %d (%s), sending a plain answer" % (which, idx + 1, e),
                     "warn")
            text = "@[%s] %s, %s here" % (sender, self.greeting(), self.place())
        return self.humanize(text)[:160]

    def operator_reply(self, rec: dict) -> str:
        """A factual answer for the operator to send by hand: who, hops, the repeaters, SNR, where we are.
        No human pass, no history: the operator reads it and may edit it before sending."""
        templates = self.msgs.get("operator_replies") or DEFAULT_MESSAGES["operator_replies"]
        hops = rec.get("hops")
        names = [n for n in (rec.get("path_names") or []) if n]
        via = "via " + ">".join(names[-4:]) if names else ("direct" if hops == 0 else "")
        snr = rec.get("snr")
        location = self.cfg.get("operator_location") or (self.cfg.get("locations") or ["here"])[0]
        try:
            text = random.choice(templates).format(
                name=rec.get("sender", "?"), hops=self.hops_words(hops), via=via, location=location,
                snr="?" if snr is None else "%+.1f" % snr, me=self.node_name)
        except (KeyError, IndexError, ValueError):
            text = "@[%s] got you %s %s here in %s" % (rec.get("sender", "?"), self.hops_words(hops), via, location)
        return " ".join(text.split())[:160]

    async def send_channel(self, idx: int, text: str, kind: str, reply_to=None, beacon_id=None) -> bool:
        if not self.mc:
            return False
        async with self.cmd_lock:
            try:
                r = await self.mc.commands.send_chan_msg(idx, text)
                ok = bool(r) and r.type.name != "ERROR"
            except Exception as e:
                self.log("Send failed: %s" % e, "warn")
                ok = False
        rec = {"ts": int(time.time()), "channel_idx": idx, "channel_name": self.channels.get(idx, str(idx)),
               "sender": self.node_name, "text": text, "kind": kind, "reply_to": reply_to, "beacon_id": beacon_id}
        rec["id"] = self.db.add_message(**rec)
        rec["path_names"] = []
        self.ui.message(rec)
        if not ok:
            self.log("Device refused the message", "warn")
        return ok

    def set_mode(self, mode: str):
        self.mode = mode
        self.log("Mode: %s" % ("bot answers and beacons" if mode == "bot" else "operator, bot silent"), "ok")

    # ------------------------------------------------------------------ beacons
    async def beacon_loop(self):
        if not self.beacon_cfg.get("enabled", True):
            return
        interval = int(self.beacon_cfg.get("interval_minutes", 10)) * 60
        first = int(self.beacon_cfg.get("first_after_s", 60))
        self.next_beacon_at = time.time() + first
        await asyncio.sleep(first)
        while True:
            if self.mode == "bot":
                await self.send_beacon()
            self.next_beacon_at = time.time() + interval
            await asyncio.sleep(interval)

    async def send_beacon(self):
        msgs = self.msgs["beacons"]
        choices = [i for i in range(len(msgs)) if i != self.beacon_idx] or [0]
        self.beacon_idx = random.choice(choices)
        try:
            text = msgs[self.beacon_idx].format(me=self.node_name, location=self.place(),
                                                daypart=self.daypart(), greeting=self.greeting())
        except (KeyError, IndexError, ValueError) as e:
            self.log("messages.json: bad placeholder in beacons line %d (%s), sending a plain beacon"
                     % (self.beacon_idx + 1, e), "warn")
            text = "%s from %s, anyone around?" % (self.greeting(), self.place())
        text = self.humanize(text)
        idx = int(self.beacon_cfg.get("channel", 1))
        b_id = self.db.add_beacon(idx, text, 0)
        self.current_beacon = (b_id, int(time.time()))
        self.counters["beacons"] += 1
        ok = await self.send_channel(idx, text, kind="beacon", beacon_id=b_id)
        self.log("Beacon %s: %s" % ("sent" if ok else "FAILED", text), "ok" if ok else "warn")

    # ------------------------------------------------------------------ repeaters
    async def repeater_loop(self):
        reps = self.cfg.get("repeaters", [])
        if not reps:
            return
        interval = int(self.cfg.get("repeater_poll_minutes", 30)) * 60
        first = int(self.cfg.get("repeater_first_after_s", 20))
        self.next_poll_at = time.time() + first
        await asyncio.sleep(first)
        while True:
            await self.poll_repeaters()
            self.next_poll_at = time.time() + interval
            await asyncio.sleep(interval)

    async def poll_repeaters(self):
        for rep in self.cfg.get("repeaters", []):
            if not self.mc:
                return
            try:
                await self.poll_one(rep)
            except Exception as e:
                self.log("%s: poll failed: %s" % (rep["name"], e), "warn")
            self.ui.repeaters(list(self.repeater_rows.values()))

    async def poll_one(self, rep: dict):
        mc = self.mc
        name, key = rep["name"], rep["pubkey"]
        prefix = key[:4].lower()
        row = {"name": name, "pubkey": key, "ok": 0, "note": ""}
        # The command lock is held only while a command goes out, not during the waits, so a message typed
        # during a poll leaves at once instead of after the whole poll.
        # 1. trace, 2-byte hash, one hop
        trace_evt = []
        sub = mc.subscribe(EventType.TRACE_DATA, lambda e: trace_evt.append(e.payload))
        try:
            async with self.cmd_lock:
                await mc.commands.send_trace(path=key[:4], flags=1)
            await asyncio.sleep(6)
        finally:
            mc.unsubscribe(sub)
        if trace_evt:
            path = trace_evt[-1].get("path") or []
            if path:
                row["trace_there"] = path[0].get("snr")
                row["trace_back"] = path[-1].get("snr") if len(path) > 1 else trace_evt[-1].get("snr")
        # 2. login + status
        pw = read_password(rep["password_file"], rep.get("password_key"))
        async with self.cmd_lock:
            await mc.commands.send_login(key, pw)
        ev = await mc.wait_for_event(EventType.LOGIN_SUCCESS, timeout=15)
        if not ev:
            row["note"] = "no login answer"
        else:
            async with self.cmd_lock:
                await mc.commands.send_statusreq(key)
            st = await mc.wait_for_event(EventType.STATUS_RESPONSE, timeout=15)
            if st:
                p = st.payload
                row.update({
                    "ok": 1, "bat_mv": p.get("bat"), "uptime_s": p.get("uptime"), "noise_floor": p.get("noise_floor"),
                    "last_rssi": p.get("last_rssi"), "nb_recv": p.get("nb_recv"), "nb_sent": p.get("nb_sent"),
                    "recv_errors": p.get("recv_errors"), "airtime": p.get("airtime"), "tx_queue": p.get("tx_queue_len"),
                    "sent_flood": p.get("sent_flood"), "sent_direct": p.get("sent_direct"),
                    "recv_flood": p.get("recv_flood"), "recv_direct": p.get("recv_direct"),
                })
            else:
                row["note"] = "no status answer"
            # 3. neighbours: the answer comes as direct messages, collected through pending_cli
            self.pending_cli[prefix] = []
            try:
                async with self.cmd_lock:
                    await mc.commands.send_cmd(key, "neighbors")
                await asyncio.sleep(8)
            finally:
                lines = "\n".join(self.pending_cli.pop(prefix, [])).splitlines()
            neigh = []
            if True:
                    for ln in lines:
                        m = re.match(r"\s*([0-9A-Fa-f]{6,8}):(\d+):(-?\d+)", ln)
                        if m:
                            nh, secs, q = m.group(1), int(m.group(2)), int(m.group(3)) / 4.0
                            nname = self.hop_name(nh[:4])
                            neigh.append((nh, nname, secs, q))
                            self.db.add_neighbor(repeater=name, neighbor=nh, neighbor_name=nname, secs_ago=secs, snr=q)
                    row["neighbors"] = neigh
        self.db.add_repeater_status(**{k: v for k, v in row.items() if k != "neighbors"})
        row["ts"] = int(time.time())
        self.repeater_rows[name] = row
        if row["ok"]:
            self.log("%s: %.2f V, up %.1f h, noise %s, trace %s/%s" % (
                name, (row.get("bat_mv") or 0) / 1000, (row.get("uptime_s") or 0) / 3600, row.get("noise_floor"),
                row.get("trace_there"), row.get("trace_back")), "ok")
        else:
            self.log("%s: %s" % (name, row["note"] or "no answer"), "warn")

    # ------------------------------------------------------------------ control
    def stop(self):
        self.stop_event.set()

    def set_pin(self, pin: str):
        self.pin = pin.strip()
