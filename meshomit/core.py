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
    # saved lines: {{key}} in a typed message, or the window that opens on {{ ; fields allowed inside
    "snippets": {
        "hop": "{hops} {via} from {location}, hope the nodes are holding up",
        "tx": "thank you",
        "hw": "how is everything?",
    },
}


def load_messages(cfg: dict, cfg_path: str | None) -> dict:
    """The text lists: messages.json next to the config (or cfg["messages_file"]), else the lists that may
    still sit in config.json (older layout), else the built-in defaults."""
    msgs = {k: (dict(v) if isinstance(v, dict) else list(v)) for k, v in DEFAULT_MESSAGES.items()}
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
        if isinstance(data.get("snippets"), dict):
            msgs["snippets"] = {str(k): str(v) for k, v in data["snippets"].items()}
    msgs["_path"] = path
    return msgs


def save_snippets(msgs: dict, cfg_path: str | None, snippets: dict) -> str:
    """Write the saved lines back into messages.json (the one next to the config when the loaded one is the
    copy bundled in the exe). The other lists in the file are kept as they are. Returns the path written."""
    path = msgs.get("_path") or "messages.json"
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled and os.path.abspath(path).startswith(os.path.abspath(bundled)):
        path = os.path.join(os.path.dirname(os.path.abspath(cfg_path or "config.json")), "messages.json")
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    data["snippets"] = dict(snippets)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    msgs["snippets"] = dict(snippets)
    msgs["_path"] = path
    return path


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
        self.cfg_path = cfg_path
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
        self.signal_tests: dict[str, dict] = {}  # repeater hash -> result of the last trace from the dialog
        self.counters = {"messages": 0, "triggers": 0, "replies": 0, "beacons": 0, "beacon_replies": 0}
        self.pin_needed = asyncio.Event()
        self.pending_cli: dict[str, list] = {}
        self.tasks: set = set()
        self.polling = False
        # contacts: the node adds everyone it hears unless manual mode is on; then adverts wait for /add
        self.manual_contacts = bool((cfg.get("contacts") or {}).get("manual", False))
        self.seen_adverts: dict[str, dict] = {}   # pubkey -> advert (contact dict) waiting for /add
        self.contacts_busy = False

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
        if self.manual_contacts:
            try:
                r = await mc.commands.set_manual_add_contacts(True)
                self.log("Contacts: manual mode, the node keeps only who you /add"
                         if r and not r.is_error() else "Contacts: could not switch the node to manual mode", "ok")
            except Exception as e:
                self.log("Contacts: manual mode not set (%s)" % e, "warn")
        mc.set_decrypt_channel_logs(True)
        mc.subscribe(EventType.NEW_CONTACT, self.on_new_contact)
        mc.subscribe(EventType.CONTACTS_FULL, self.on_contacts_full)
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
    @staticmethod
    def advert_name(c: dict) -> str:
        return c.get("adv_name") or (c.get("public_key") or "")[:8]

    def on_new_contact(self, e):
        """An advert the node reports: added by itself (automatic mode) or waiting for /add (manual mode)."""
        c = dict(e.payload or {})
        key = c.get("public_key")
        if not key:
            return
        c["seen"] = int(time.time())
        name = self.advert_name(c)
        kind = self.CONTACT_TYPES.get(c.get("type"), "node")
        if self.manual_contacts:
            self.seen_adverts[key] = c
            self.log("Advert from %s (%s): /add %s to keep it" % (name, kind, name), "ok")
        else:
            if self.mc:
                self.mc.contacts[key] = c
            self.log("New contact: %s (%s)" % (name, kind), "ok")

    def on_contacts_full(self, e):
        self.log("The node's contact table is full: /contacts clear yes, or /forget NAME, to make room", "warn")

    def contacts_path(self, name: str = "contacts.json") -> str:
        return os.path.join(os.path.dirname(os.path.abspath(self.cfg_path or "config.json")), name)

    def my_contacts(self) -> list:
        """The contacts you added yourself, kept in contacts.json next to the config."""
        p = self.contacts_path()
        if os.path.exists(p):
            with open(p, encoding="utf-8-sig") as f:
                return json.load(f)
        return []

    def save_my_contacts(self, rows: list) -> None:
        with open(self.contacts_path(), "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1, ensure_ascii=False, default=str)

    def pending_adverts(self) -> list:
        """Adverts waiting for /add, newest first: the library's pending list plus the ones seen here."""
        rows = dict(self.seen_adverts)
        if self.mc:
            for k, c in (getattr(self.mc, "pending_contacts", None) or {}).items():
                rows.setdefault(k, dict(c))
        return sorted(rows.values(), key=lambda c: -(c.get("seen") or c.get("last_advert") or 0))

    def find_advert(self, name: str) -> dict | None:
        want = name.lower().strip()
        rows = self.pending_adverts()
        hits = [c for c in rows if self.advert_name(c).lower() == want] or \
               [c for c in rows if want in self.advert_name(c).lower()]
        return hits[0] if hits else None

    async def export_contacts(self) -> tuple[str, int]:
        """A dated backup of the node's whole contact list, next to the config."""
        if not self.mc:
            raise ConnectionError("not connected")
        rows = [dict(c, public_key=k) for k, c in self.mc.contacts.items()]
        p = self.contacts_path("contacts-backup-%s.json" % time.strftime("%Y%m%d-%H%M"))
        with open(p, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1, ensure_ascii=False, default=str)
        return p, len(rows)

    async def add_contact(self, name: str) -> str:
        c = self.find_advert(name)
        if not c:
            return "no advert from %s seen yet: ask them to press Advert, or /add with no name for the list" % name
        if not self.mc:
            return "not connected"
        async with self.cmd_lock:
            r = await self.mc.commands.add_contact({k: v for k, v in c.items() if k != "seen"})
        if not r or r.type.name == "ERROR":
            return "the node refused the contact (table full?)"
        key = c["public_key"]
        self.mc.contacts[key] = c
        self.seen_adverts.pop(key, None)
        try:
            self.mc.pop_pending_contact(key)
        except Exception:
            pass
        mine = [m for m in self.my_contacts() if m.get("public_key") != key] + [c]
        self.save_my_contacts(mine)
        self.contacts_loaded = True
        self.log("Contact added: %s" % self.advert_name(c), "ok")
        return "%s added (%d contacts on the node, %d in contacts.json)" % (self.advert_name(c), len(self.mc.contacts), len(mine))

    async def forget_contact(self, name: str) -> str:
        if not self.mc:
            return "not connected"
        hits = [(k, c) for k, c in self.mc.contacts.items() if (c.get("adv_name") or "").lower() == name.lower().strip()]
        if not hits:
            return "no contact named %s" % name
        key, c = hits[0]
        async with self.cmd_lock:
            r = await self.mc.commands.remove_contact(key)
        if not r or r.type.name == "ERROR":
            return "the node refused to remove %s" % name
        self.mc.contacts.pop(key, None)
        self.save_my_contacts([m for m in self.my_contacts() if m.get("public_key") != key])
        self.log("Contact removed: %s" % name, "ok")
        return "%s removed (%d contacts on the node)" % (name, len(self.mc.contacts))

    async def clear_contacts(self, progress) -> str:
        """Back the list up, then remove every contact from the node. progress(text) reports along the way."""
        if not self.mc:
            return "not connected"
        if self.contacts_busy:
            return "already working on the contact list"
        self.contacts_busy = True
        try:
            path, n = await self.export_contacts()
            progress("Backup of %d contacts written to %s" % (n, os.path.basename(path)))
            keys = list(self.mc.contacts)
            done = failed = 0
            for i, key in enumerate(keys, 1):
                if not self.mc:
                    break
                async with self.cmd_lock:
                    try:
                        r = await self.mc.commands.remove_contact(key)
                        ok = bool(r) and r.type.name != "ERROR"
                    except Exception:
                        ok = False
                if ok:
                    done += 1
                    self.mc.contacts.pop(key, None)
                else:
                    failed += 1
                if i % 25 == 0:
                    progress("Removing contacts: %d of %d" % (i, len(keys)))
            self.contacts_loaded = bool(self.mc and self.mc.contacts)
            self.log("Contacts cleared: %d removed, %d refused" % (done, failed), "ok")
            return "%d contacts removed, %d refused; backup in %s" % (done, failed, os.path.basename(path))
        finally:
            self.contacts_busy = False

    async def restore_contacts(self, progress) -> str:
        """Add every contact of contacts.json back to the node (after a reset, or on another node)."""
        if not self.mc:
            return "not connected"
        mine = self.my_contacts()
        done = 0
        for c in mine:
            async with self.cmd_lock:
                try:
                    r = await self.mc.commands.add_contact({k: v for k, v in c.items() if k != "seen"})
                    ok = bool(r) and r.type.name != "ERROR"
                except Exception:
                    ok = False
            if ok:
                done += 1
                self.mc.contacts[c["public_key"]] = c
        self.contacts_loaded = bool(self.mc.contacts)
        return "%d of %d contacts from contacts.json are on the node" % (done, len(mine))

    async def set_manual(self, on: bool) -> str:
        self.manual_contacts = on
        self.cfg.setdefault("contacts", {})["manual"] = on
        if self.mc:
            async with self.cmd_lock:
                try:
                    r = await self.mc.commands.set_manual_add_contacts(on)
                    if not r or r.is_error():
                        return "the node did not accept the setting"
                except Exception as e:
                    return "could not set it: %s" % e
        return ("manual: the node keeps only who you /add; adverts wait in /add" if on
                else "automatic: the node adds everyone it hears")

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

    @staticmethod
    def battery_percent(mv) -> int | None:
        """Rough state of charge of a single lithium cell from its resting voltage."""
        if not mv:
            return None
        v = mv / 1000.0
        points = [(4.15, 100), (4.05, 90), (3.95, 75), (3.85, 60), (3.78, 45), (3.70, 30), (3.60, 15), (3.45, 5),
                  (3.30, 0)]
        if v >= points[0][0]:
            return 100
        for (v1, p1), (v2, p2) in zip(points, points[1:]):
            if v2 <= v <= v1:
                return int(round(p2 + (p1 - p2) * (v - v2) / (v1 - v2)))
        return 0

    def own_repeater(self, hash_or_name: str) -> bool:
        """Is this neighbour one of the repeaters in config.json (by name or hash prefix)?"""
        h = (hash_or_name or "").lower()
        for r in self.cfg.get("repeaters", []):
            if h == r["name"].lower() or (len(h) >= 2 and r["pubkey"].lower().startswith(h[:4])):
                return True
        return False

    def repeater_report(self, name: str) -> dict:
        """Everything the screen shows about one of our repeaters: last poll, battery with a rough percentage
        and the drain over the last day, the strongest neighbour that is not ours, and the neighbour count."""
        row = self.repeater_rows.get(name) or self.db.last_repeater_row(name) or {"name": name, "ok": 0, "note": ""}
        rep = dict(row)
        mv = rep.get("bat_mv")
        rep["percent"] = self.battery_percent(mv)
        rep["mv_per_day"] = rep["days_left"] = None
        if mv and rep.get("ts"):
            ts = int(rep["ts"])
            old = self.db.battery_at(name, ts - 20 * 3600) or self.db.battery_oldest_since(name, ts - 24 * 3600)
            if old and ts - old[0] >= 6 * 3600:
                days = (ts - old[0]) / 86400.0
                rep["mv_per_day"] = (old[1] - mv) / days
                # days left from the charge estimate, not the voltage: the top of the curve drops fast
                pct_old, pct_now = self.battery_percent(old[1]), rep["percent"]
                if pct_old is not None and pct_now is not None and pct_old - pct_now >= 1:
                    rep["days_left"] = pct_now / ((pct_old - pct_now) / days)
        best_of: dict = {}  # one entry per neighbour, the strongest report (retried polls report twice)
        for h, n, s, q in rep.get("neighbors") or self.db.latest_neighbors(name):
            k = (h or "").lower()[:4]
            if k not in best_of or (q or -99) > (best_of[k][3] or -99):
                best_of[k] = (h, n, s, q)
        neigh = list(best_of.values())
        others = [(h, n, s, q) for h, n, s, q in neigh if not self.own_repeater(n) and not self.own_repeater(h)]
        rep["neighbors_all"] = sorted(neigh, key=lambda x: -(x[3] or -99))
        rep["others"] = sorted(others, key=lambda x: -(x[3] or -99))
        rep["best"] = rep["others"][0] if rep["others"] else None
        return rep

    def save_snippets(self, snippets: dict) -> str:
        return save_snippets(self.msgs, self.cfg_path, snippets)

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
        first = int(self.cfg.get("repeater_first_after_s", 20))
        self.next_poll_at = time.time() + first if self.cfg.get("repeaters") else None
        await asyncio.sleep(first)
        while True:
            if not self.cfg.get("repeaters"):  # none yet; the repeater dialog can add one at any time
                self.next_poll_at = None
                await asyncio.sleep(10)
                continue
            interval = int(self.cfg.get("repeater_poll_minutes", 30)) * 60
            await self.poll_repeaters()
            self.next_poll_at = time.time() + interval
            await asyncio.sleep(interval)

    async def trace(self, hash4: str) -> tuple | None:
        """A trace through one repeater (2-byte hash, one hop): (SNR at the repeater of our packet, SNR here
        of its answer), or None when nothing comes back within 6 seconds. Needs no password."""
        mc = self.mc
        trace_evt = []
        sub = mc.subscribe(EventType.TRACE_DATA, lambda e: trace_evt.append(e.payload))
        try:
            async with self.cmd_lock:
                await mc.commands.send_trace(path=hash4, flags=1)
            await asyncio.sleep(6)
        finally:
            mc.unsubscribe(sub)
        if not trace_evt:
            return None
        path = trace_evt[-1].get("path") or []
        if not path:
            return None
        there = path[0].get("snr")
        back = path[-1].get("snr") if len(path) > 1 else trace_evt[-1].get("snr")
        return there, back

    # ------------------------------------------------------------------ the repeater dialog
    def _blank_candidate(self, name: str, key, h: str, mine: bool = False) -> dict:
        return {"name": name, "key": key, "hash": h, "mine": mine, "pkts": 0, "snr": None, "last_heard": None,
                "hops": None, "km": None, "dir": None, "last_advert": None, "closest": False}

    def repeater_candidates(self) -> list[dict]:
        """Every repeater we could poll or test: our own (config.json), the repeaters in the node's contact
        list, and the hashes that relayed packets to us in the last day. Each dict has name, key (None when
        only a hash is known), hash (2 to 6 hex chars), mine, pkts and snr as the last hop of what we heard
        in 24 h, last_heard, hops (the node's path length), km and dir, last_advert, closest. Our own come
        first, then the strongest signal; 'closest' marks the one heard best."""
        now = int(time.time())
        cands: dict[str, dict] = {}  # 4-hex prefix (or ~hash) -> candidate
        me = (self.mc.self_info or {}) if self.mc else {}
        mlat, mlon = me.get("adv_lat") or 0.0, me.get("adv_lon") or 0.0

        def add(key: str, name: str, mine: bool = False, c: dict | None = None) -> dict:
            k = key.lower()
            d = cands.setdefault(k[:4], self._blank_candidate(name, k, k[:4]))
            if mine:
                d["mine"], d["name"] = True, name
            if c:
                hops = c.get("out_path_len")
                d["hops"] = hops if hops is not None and hops >= 0 else None
                d["last_advert"] = c.get("last_advert") or None
                lat, lon = c.get("adv_lat") or 0.0, c.get("adv_lon") or 0.0
                if (lat or lon) and (mlat or mlon):
                    d["km"], d["dir"] = distance_km(mlat, mlon, lat, lon)
            return d

        for r in self.cfg.get("repeaters", []):
            add(r["pubkey"], r["name"], mine=True)
        if self.mc:
            for key, c in self.mc.contacts.items():
                if c.get("type") == 2:
                    add(key, c.get("adv_name") or key[:8], c=c)
        # what relayed packets to us in the last day, by the hash of the last hop (1, 2 or 3 bytes)
        loose = []
        for h, n, snr, last in self.db.last_hop_stats(now - 24 * 3600):
            h = (h or "").lower()
            if len(h) < 2:
                continue
            hit = [d for d in cands.values() if d["key"] and (d["key"].startswith(h) or h.startswith(d["hash"]))]
            if hit:
                d = hit[0]
                d["pkts"] += n
                d["snr"] = snr if d["snr"] is None else max(d["snr"], snr)
                d["last_heard"] = last if d["last_heard"] is None else max(d["last_heard"], last)
            else:
                loose.append((h, n, snr, last))
        # hashes that match no contact: the short forms join the longest one they fit
        loose.sort(key=lambda x: -len(x[0]))
        for h, n, snr, last in loose:
            d = next((d for d in cands.values() if d["key"] is None and d["hash"].startswith(h)), None)
            if d is None:
                known = self.known.get(h[:4]) or self.known.get(h[:2])
                d = cands.setdefault("~" + h, self._blank_candidate(known or h.upper(), None, h))
            d["pkts"] += n
            d["snr"] = snr if d["snr"] is None else max(d["snr"], snr)
            d["last_heard"] = last if d["last_heard"] is None else max(d["last_heard"], last)
        rows = list(cands.values())
        rows.sort(key=lambda d: (0 if d["mine"] else 1, -(d["snr"] if d["snr"] is not None else -999),
                                 -d["pkts"], d["name"].lower()))
        heard = [d for d in rows if d["snr"] is not None]
        if heard:
            max(heard, key=lambda d: d["snr"])["closest"] = True
        return rows

    async def test_signal(self, cand: dict) -> dict:
        """A trace through one repeater, to see how well it hears us and we hear it. Needs no password."""
        h = cand["hash"][:4]
        tr = await self.trace(h) if self.mc and len(h) == 4 else None
        res = {"ts": int(time.time()), "ok": bool(tr), "there": tr[0] if tr else None, "back": tr[1] if tr else None}
        self.signal_tests[h] = res
        if tr:
            self.log("Signal test %s: it hears us at %s dB, we hear it at %s dB" % (cand["name"], tr[0], tr[1]), "ok")
        else:
            self.log("Signal test %s: no answer to the trace" % cand["name"], "warn")
        return res

    def save_config_keys(self, **keys) -> None:
        """Write some top-level keys back to config.json, leaving the rest of the file as it is."""
        path = self.cfg_path or "config.json"
        try:
            with open(path, encoding="utf-8-sig") as f:
                on_disk = json.load(f)
        except (OSError, ValueError):
            on_disk = {}
        on_disk.update(keys)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(on_disk, f, indent=2, ensure_ascii=False)

    def add_own_repeater(self, name: str, key: str, password: str) -> dict:
        """Make a repeater one of ours: the password goes to passwords/<key prefix>.txt next to config.json,
        the entry (with that relative path) to the repeaters list in config.json. Returns the entry."""
        folder = self.contacts_path("passwords")
        os.makedirs(folder, exist_ok=True)
        rel = "passwords/%s.txt" % key[:8].lower()
        with open(os.path.join(folder, key[:8].lower() + ".txt"), "w", encoding="utf-8") as f:
            f.write(password.strip() + "\n")
        reps = [r for r in self.cfg.get("repeaters", []) if r["pubkey"].lower() != key.lower()]
        entry = {"name": name, "pubkey": key.lower(), "password_file": rel, "password_key": None}
        reps.append(entry)
        self.cfg["repeaters"] = reps
        self.known[key[:4].lower()] = name
        self.known[key[:2].lower()] = name
        self.save_config_keys(repeaters=reps)
        return entry

    def forget_own_repeater(self, name: str) -> bool:
        """Take a repeater off our list (the password file stays). True when it was there."""
        reps = [r for r in self.cfg.get("repeaters", []) if r["name"] != name]
        if len(reps) == len(self.cfg.get("repeaters", [])):
            return False
        self.cfg["repeaters"] = reps
        self.repeater_rows.pop(name, None)
        self.save_config_keys(repeaters=reps)
        return True

    async def poll_repeaters(self):
        if self.polling:  # the r key pressed during a poll: one at a time
            return
        self.polling = True
        try:
            for rep in self.cfg.get("repeaters", []):
                if not self.mc:
                    return
                try:
                    await self.poll_one(rep)
                except Exception as e:
                    self.log("%s: poll failed: %s" % (rep["name"], e), "warn")
                self.ui.repeaters(list(self.repeater_rows.values()))
        finally:
            self.polling = False

    async def poll_one(self, rep: dict):
        mc = self.mc
        name, key = rep["name"], rep["pubkey"]
        prefix = key[:4].lower()
        row = {"name": name, "pubkey": key, "ok": 0, "note": ""}
        # The command lock is held only while a command goes out, not during the waits, so a message typed
        # during a poll leaves at once instead of after the whole poll.
        # 1. trace, 2-byte hash, one hop
        tr = await self.trace(key[:4])
        if tr:
            row["trace_there"], row["trace_back"] = tr
        # 2. login + status, each tried twice: a busy repeater drops the odd packet
        pw = read_password(self.contacts_path(rep["password_file"]), rep.get("password_key"))
        ev = None
        for attempt in range(2):
            async with self.cmd_lock:
                await mc.commands.send_login(key, pw)
            ev = await mc.wait_for_event(EventType.LOGIN_SUCCESS, timeout=15)
            if ev:
                break
        if not ev:
            row["note"] = "no login answer (2 tries)"
        else:
            st = None
            for attempt in range(2):
                async with self.cmd_lock:
                    await mc.commands.send_statusreq(key)
                st = await mc.wait_for_event(EventType.STATUS_RESPONSE, timeout=15)
                if st:
                    break
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
                row["note"] = "no status answer (2 tries)"
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
