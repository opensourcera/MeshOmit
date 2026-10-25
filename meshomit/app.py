# MeshOmit, Copyright (c) 2026 opensourcera. MIT License, see LICENSE.
"""MeshOmit screen (Textual), styled after a classic IRC client: windows per channel, room and private chat,
a first-run setup and a stats dashboard."""
import asyncio
import json
import os
import re
import secrets
import sys
import time
import zlib

from rich.style import Style
from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (Button, DataTable, Footer, Header, Input, Label, OptionList, RadioButton, RadioSet,
                             RichLog, Select, Sparkline, Static)
from textual.widgets.option_list import Option

from . import connection
from .core import Engine
from .db import Db

CSS = """
Screen { layout: vertical; background: #000000; }
Header { background: #1a1a4a; color: #e0e0ff; }
Footer { background: #1a1a4a; }
#body { height: 1fr; }
#left { width: 3fr; }
#right { width: 1fr; min-width: 40; max-width: 56; }
#conversation { height: 1fr; background: #000000; color: #FFFFFF; border: round #4040a0; padding: 0 1; scrollbar-color: #4040a0;
    link-color: auto; link-background: transparent; link-style: none;
    link-color-hover: #000000; link-background-hover: #C8A2C8; link-style-hover: bold; }
#sendbar { height: 1; background: #000000; }
#send_to { width: auto; height: 1; background: #202060; color: #FFFFFF; padding: 0 1; }
#send_line { width: 1fr; height: 1; border: none; padding: 0 1; background: #101010; color: #FFFFFF; }
#send_line:focus { border: none; background: #181838; }
#status { height: auto; background: #000000; border: round #2080a0; padding: 0 1; }
#channels { height: 9; background: #000000; border: round #4040a0; }
#nicks { height: 11; background: #000000; border: round #40a040; }
#channels > .option-list--option-highlighted { background: #202060; }
#nicks > .option-list--option-highlighted { background: #204020; }
#repeaters { height: auto; max-height: 14; background: #000000; border: round #2080a0; padding: 0 1; }
#events { height: 1fr; background: #000000; border: round #a08020; padding: 0 1; }
#pin_box { width: 60; height: auto; border: thick #4040a0; background: #101030; padding: 1 2; }
FieldScreen { align: left bottom; }
SnippetScreen { align: left bottom; }
PeopleScreen { align: left bottom; }
#people_box { width: 90; height: auto; max-height: 18; border: round #C8A2C8; background: #101020; margin: 0 0 2 1; }
#people_box Label { color: #C8A2C8; padding: 0 1; }
#people { height: auto; max-height: 14; background: #101020; }
#snip_box { width: 110; height: auto; max-height: 20; border: round #C8A2C8; background: #101020; margin: 0 0 2 1; }
#snip_box Label { color: #C8A2C8; padding: 0 1; }
#snips { height: auto; max-height: 12; background: #101020; }
#snip_box Button { min-width: 10; margin: 0 1; }
#snip_edit { width: 110; height: auto; border: thick #C8A2C8; background: #1a1026; padding: 1 2; }
#snip_edit Label.h { color: #C8A2C8; text-style: bold; }
#snip_edit Input { margin-bottom: 1; }
#field_box { width: 70; height: auto; max-height: 16; border: round #C8A2C8; background: #101020; margin: 0 0 2 1; }
#field_box Label { color: #C8A2C8; padding: 0 1; }
#fields { height: auto; max-height: 12; background: #101020; }
#pin_box Label { margin-bottom: 1; }

/* operator mode: lilac */
Screen.operator Header { background: #5a3a7a; color: #f4e6ff; }
Screen.operator Footer { background: #5a3a7a; }
Screen.operator #conversation { border: round #C8A2C8; scrollbar-color: #C8A2C8; }
Screen.operator #status { border: round #C8A2C8; }
Screen.operator #send_to { background: #5a3a7a; color: #f4e6ff; }
Screen.operator #send_line:focus { background: #2a1a3a; }
Screen.operator #channels { border: round #C8A2C8; }
Screen.operator #nicks { border: round #C8A2C8; }
Screen.operator #repeaters { border: round #C8A2C8; }
Screen.operator #events { border: round #C8A2C8; }

/* send window */
#send_box { width: 150; height: auto; border: thick #C8A2C8; background: #1a1026; padding: 1 2; }
#send_box Label.h { color: #C8A2C8; text-style: bold; }
#send_text { width: 144; }
#send_count { color: #A0A0A0; }
#emo_row { height: auto; }
#emo_row Button { min-width: 6; width: auto; margin: 0 1 0 0; background: #3a2a4a; color: #FFFFFF; border: none; height: 1; }
#quick_list { height: 7; border: round #5a3a7a; }
#send_msg { color: #FF8000; }
#send_box Select { width: 60; }

/* room window */
#room_box { width: 100; height: auto; border: thick #C8A2C8; background: #1a1026; padding: 1 2; }
#room_box Label.h { color: #C8A2C8; text-style: bold; margin-top: 1; }
#room_box Button { margin: 1 1 0 0; }
#rep_box { width: 90%; max-width: 150; height: auto; border: thick #C8A2C8; background: #1a1026; padding: 1 2; }
#rep_box Label { width: 1fr; }
#rep_box Label.h { color: #C8A2C8; text-style: bold; }
#rep_box DataTable { height: auto; max-height: 16; background: #000000; margin: 1 0 0 0; }
#rep_box Horizontal { height: auto; }
#rep_box Button { margin: 1 1 0 0; }
#pw_box { width: 90; height: auto; border: thick #C8A2C8; background: #1a1026; padding: 1 2; }
#pw_box Label { width: 1fr; }
#pw_box Label.h { color: #C8A2C8; text-style: bold; }
#pw_box Horizontal { height: auto; }
#pw_box Button { margin: 1 1 0 0; }
#invite_list { height: 6; border: round #5a3a7a; }
#room_msg { color: #FF8000; }

/* setup */
#setup_box { width: 90; height: 90%; border: thick #4040a0; background: #101030; padding: 1 2; }
#setup_scroll { height: 1fr; }
#setup_foot, #setup_foot Horizontal { height: auto; }
#setup_box Label.h { color: #FFFF00; text-style: bold; margin-top: 1; }
#setup_box Input { margin-bottom: 0; }
#setup_box Button { margin: 1 1 0 0; }
#ble_part, #serial_part, #tcp_part { height: auto; }
#ble_list { height: 10; border: round #4040a0; }
#serial_list { height: 6; border: round #4040a0; }
.hidden { display: none; }
#setup_msg { color: #FF8000; }

/* dashboard */
DashboardScreen { background: #000000; }
#dash { height: 1fr; padding: 0 1; }
.cards { height: auto; }
.card { width: 1fr; height: auto; border: round #2080a0; padding: 0 1; margin: 0 1 0 0; background: #000000; }
.card.purple { border: round #8040c0; }
.card.green { border: round #40a040; }
.card.orange { border: round #c08020; }
.spark_row { height: auto; }
.spark_box { width: 1fr; height: auto; border: round #303060; padding: 0 1; margin: 0 1 0 0; }
.spark_box Label { color: #A0A0A0; }
Sparkline { height: 3; }
#sp_msgs > .sparkline--max-color { color: #00FFFF; }
#sp_msgs > .sparkline--min-color { color: #004455; }
#sp_tests > .sparkline--max-color { color: #FFFF00; }
#sp_tests > .sparkline--min-color { color: #555500; }
#sp_replies > .sparkline--max-color { color: #00FF00; }
#sp_replies > .sparkline--min-color { color: #004400; }
#sp_beacon > .sparkline--max-color { color: #C080FF; }
#sp_beacon > .sparkline--min-color { color: #402060; }
.tables { height: auto; }
.tables DataTable { width: 1fr; height: auto; max-height: 16; border: round #303060; margin: 0 1 0 0; background: #000000; }
#dash_replies { height: auto; border: round #303060; padding: 0 1; margin: 0 1 0 0; }
"""

# the classic mIRC palette at full brightness, one per nick
NICK_COLORS = ["#00FFFF", "#00FF00", "#FFFF00", "#FF00FF", "#FF5555", "#FF8000", "#5599FF", "#55FF99",
               "#FFD700", "#FF69B4", "#00FFAA", "#DA70D6", "#F0E68C", "#7FFFD4", "#FFA07A", "#EE82EE",
               "#7FFF00", "#87CEFA", "#FFB347", "#40E0D0"]
CHANNEL_COLORS = {"Public": "#BBBBBB", "#test": "#FF8000"}


def nick_color(name: str) -> str:
    return NICK_COLORS[zlib.crc32(name.encode("utf-8", "ignore")) % len(NICK_COLORS)]


class PinScreen(ModalScreen[str]):
    def __init__(self, node: str, reason: str = ""):
        super().__init__()
        self.node = node
        self.reason = reason

    def compose(self) -> ComposeResult:
        with Vertical(id="pin_box"):
            yield Label("Bluetooth PIN for %s\n%s\nThe six digits are shown on the node's screen." % (
                self.node, self.reason))
            yield Input(placeholder="123456", max_length=6, id="pin")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())


class SetupScreen(ModalScreen[dict]):
    """First run: how to reach the node and where we are. Returns the config dict, or None to quit."""

    def __init__(self, defaults: dict):
        super().__init__()
        self.defaults = defaults
        self.ble_rows: list = []

    def compose(self) -> ComposeResult:
        with Vertical(id="setup_box"):
            with VerticalScroll(id="setup_scroll"):
                yield Label("MeshOmit setup", classes="h")
                yield Label("How is the MeshCore node connected to this computer?")
                with RadioSet(id="conn_type"):
                    yield RadioButton("Bluetooth LE", value=True, id="rb_ble")
                    yield RadioButton("USB serial", id="rb_serial")
                    yield RadioButton("WiFi / TCP", id="rb_tcp")
                with Vertical(id="ble_part"):
                    yield Label("Pick the node from the list (it fills while the scan runs), or type its address:")
                    yield Input(placeholder="AA:BB:CC:DD:EE:FF", id="ble_addr")
                    yield Button("Scan again", id="scan")
                    yield OptionList(id="ble_list")
                with Vertical(id="serial_part", classes="hidden"):
                    yield Label("Serial port:")
                    yield Input(placeholder="COM6 or /dev/ttyUSB0", id="serial_port")
                    yield OptionList(id="serial_list")
                with Vertical(id="tcp_part", classes="hidden"):
                    yield Label("Host and port of the node:")
                    yield Input(placeholder="192.168.1.50", id="tcp_host")
                    yield Input(placeholder="5000", id="tcp_port", value="5000")
                yield Label("Where you are, a few names separated by commas (the bot uses one at random):", classes="h")
                yield Input(placeholder="Springfield, Downtown, Riverside", id="locations")
                yield Label("Your node's name (leave empty to take it from the node):", classes="h")
                yield Label("Your own repeaters come later: once connected, click the Repeaters panel, pick them "
                            "from the list and give their admin password.", classes="h")
                yield Input(placeholder="", id="node_name")
            with Vertical(id="setup_foot"):  # always visible under the scrolling part
                yield Label("", id="setup_msg")
                with Horizontal():
                    yield Button("Save and start", variant="success", id="save")
                    yield Button("Quit", id="quit")
    
    def on_mount(self) -> None:
        ports = connection.serial_ports()
        lst = self.query_one("#serial_list", OptionList)
        for port, desc in ports:
            lst.add_option("%s  %s" % (port, desc))
        if not ports:
            lst.add_option("(no serial ports found)")
        self.run_worker(self.scan(), exclusive=True, group="scan", name="scan")

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        which = event.pressed.id
        for part, rb in (("#ble_part", "rb_ble"), ("#serial_part", "rb_serial"), ("#tcp_part", "rb_tcp")):
            self.query_one(part).set_class(rb != which, "hidden")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter in any field of the form is the same as Save and start."""
        event.stop()
        self.save()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "scan":
            self.run_worker(self.scan(), exclusive=True, group="scan", name="scan")
        elif event.button.id == "save":
            self.save()
        elif event.button.id == "quit":
            self.dismiss(None)

    SCAN_SECONDS = 8

    def show_ble_rows(self, scanning: bool) -> None:
        """Redraw the device list from self.ble_rows, MeshCore nodes first, and the line under it."""
        lst = self.query_one("#ble_list", OptionList)
        msg = self.query_one("#setup_msg", Label)
        self.ble_rows.sort(key=connection._scan_order)
        lst.clear_options()
        for name, addr in self.ble_rows:
            t = Text("%-24s " % (name or "(no name)")[:24],
                     style="bold #80FF80" if "meshcore" in (name or "").lower() else "")
            t.append(addr, style="grey70")
            lst.add_option(Option(t))
        nodes = sum(1 for name, _ in self.ble_rows if "meshcore" in (name or "").lower())
        if scanning:
            msg.update("Scanning for %d seconds... %d devices so far, %d of them MeshCore nodes."
                       % (self.SCAN_SECONDS, len(self.ble_rows), nodes))
        elif nodes:
            msg.update("%d devices found. MeshCore nodes are listed first in green: pick yours." % len(self.ble_rows))
        else:
            msg.update("%d devices found, none of them a MeshCore node. A node that is connected to a phone, or to "
                       "another copy of MeshOmit, does not show up: disconnect it there (or turn the phone's "
                       "Bluetooth off) and press Scan again." % len(self.ble_rows))

    async def scan(self):
        msg = self.query_one("#setup_msg", Label)
        btn = self.query_one("#scan", Button)
        btn.disabled = True
        self.ble_rows = []
        self.show_ble_rows(scanning=True)

        def found(name, addr):
            try:
                self.ble_rows = [r for r in self.ble_rows if r[1] != addr] + [(name, addr)]
                self.show_ble_rows(scanning=True)
            except Exception as e:  # never let a drawing problem silence the scan
                msg.update("Scan: %s" % e)

        try:
            rows = await connection.scan_ble(self.SCAN_SECONDS, found)
        except Exception as e:
            msg.update("Scan failed: %s. Is Bluetooth switched on in Windows settings?" % e)
            return
        finally:
            btn.disabled = False
        self.ble_rows = list(rows)
        self.show_ble_rows(scanning=False)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "ble_list":
            if event.option_index < len(self.ble_rows):
                self.query_one("#ble_addr", Input).value = self.ble_rows[event.option_index][1]
        elif event.option_list.id == "serial_list":
            text = str(event.option.prompt)
            if not text.startswith("("):
                self.query_one("#serial_port", Input).value = text.split()[0]

    def save(self):
        msg = self.query_one("#setup_msg", Label)
        cfg = json.loads(json.dumps(self.defaults))
        pressed = self.query_one("#conn_type", RadioSet).pressed_button
        kind = {"rb_ble": "ble", "rb_serial": "serial", "rb_tcp": "tcp"}.get(pressed.id if pressed else "", "ble")
        if kind == "ble":
            addr = self.query_one("#ble_addr", Input).value.strip().upper()
            if len(addr.replace(":", "").replace("-", "")) != 12:
                msg.update("Please give the Bluetooth address or pick a device from the scan.")
                return
            cfg["connection"] = {"type": "ble", "address": addr, "pin": None}
        elif kind == "serial":
            port = self.query_one("#serial_port", Input).value.strip()
            if not port:
                msg.update("Please give the serial port.")
                return
            cfg["connection"] = {"type": "serial", "port": port, "baud": 115200}
        else:
            host = self.query_one("#tcp_host", Input).value.strip()
            port = self.query_one("#tcp_port", Input).value.strip() or "5000"
            if not host or not port.isdigit():
                msg.update("Please give the host and a numeric port.")
                return
            cfg["connection"] = {"type": "tcp", "host": host, "port": int(port)}
        locs = [x.strip() for x in self.query_one("#locations", Input).value.split(",") if x.strip()]
        if not locs:
            msg.update("Please give at least one place name.")
            return
        cfg["locations"] = locs
        cfg["node_name"] = self.query_one("#node_name", Input).value.strip()
        cfg["repeaters"] = []
        cfg["known_prefixes"] = {}
        cfg.pop("_help", None)
        self.dismiss(cfg)


FIELDS = [
    ("name", "the station you address"),
    ("hops", "hops of its last message"),
    ("via", "the repeaters it came through"),
    ("snr", "SNR of its last message, dB"),
    ("rssi", "RSSI of its last message, dBm"),
    ("heard", "when its last message was heard"),
    ("location", "your place (operator_location)"),
    ("time", "the time now"),
    ("me", "your node's name"),
]


EMOJI_FOR = {":)": "🙂", ";)": "😉", ":D": "😃", ":P": "😛", ":(": "🙁",
             "<3": "❤️", "o/": "👋", "^^": "😊", "73": "📻", "+1": "👍",
             ":-)": "🙂", ";-)": "😉", ":-D": "😃", ":-(": "🙁", ":O": "😮",
             "xD": "😆", ":*": "😘", "B)": "😎", "<3<3": "💖", "\\o/": "🎉"}


class FieldScreen(ModalScreen[str]):
    """The list that opens on `{`: a field (filled in when the message is sent) or an emoticon. Emoticons are
    shown as the picture they stand for and inserted as the text form, which every mesh device can show."""

    BINDINGS = [Binding("escape", "cancel", "Cancel"), Binding("left_curly_bracket", "snippets", "Saved lines")]

    def __init__(self, values: dict, emoticons: list | None = None):
        super().__init__()
        self.values = values
        self.emoticons = emoticons or []

    def action_snippets(self) -> None:
        self.dismiss("snippets")

    def compose(self) -> ComposeResult:
        with Vertical(id="field_box"):
            yield Label("Fields are filled in when you send; emoticons go in as text. Enter picks, Escape closes, "
                        "{ again opens your saved lines.")
            lst = OptionList(id="fields")
            for key, what in FIELDS:
                t = Text("{%s}" % key, style="bold #FFFF00")
                t.append("  %-32s" % what, style="#A0A0A0")
                t.append(" " + str(self.values.get(key, "?"))[:22], style="#80FF80")
                lst.add_option(Option(t, id="field:" + key))
            if self.emoticons:
                lst.add_option(None)  # a separator line
                for emo in self.emoticons:
                    t = Text("%-3s " % EMOJI_FOR.get(emo, " "), style="bold")
                    t.append("%-6s" % emo, style="bold #FFFF00")
                    t.append("  sent as the text on the left", style="#A0A0A0")
                    lst.add_option(Option(t, id="emo:" + emo))
            yield lst

    def on_mount(self) -> None:
        lst = self.query_one("#fields", OptionList)
        lst.highlighted = 0
        lst.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)


class PeopleScreen(ModalScreen[str]):
    """The list that opens on @: the stations heard lately, those of the current window first. Enter puts a
    mention of the chosen one in the message."""

    BINDINGS = [Binding("escape", "cancel", "Close")]

    def __init__(self, rows: list):
        super().__init__()
        self.rows = rows  # (name, where, hops, ago_seconds, is_contact, in_this_window)

    def compose(self) -> ComposeResult:
        with Vertical(id="people_box"):
            yield Label("Heard in the last 3 hours, this window first. Enter mentions the station (@[name]), "
                        "Escape closes.")
            lst = OptionList(id="people")
            for name, where, hops, ago, contact, here in self.rows:
                t = Text("%-24s" % name[:24], style=("bold " if here else "") + nick_color(name))
                t.append(" %-12s" % (where or "")[:12], style="#A0A0A0")
                t.append(" %-8s" % ("" if hops is None else "direct" if hops == 0 else "%dh" % hops), style="grey70")
                t.append(" %-7s" % MeshOmitApp.ago(ago), style="grey50")
                t.append(" contact" if contact else "", style="#80FF80")
                lst.add_option(Option(t, id="p:" + name))
            if not self.rows:
                lst.add_option(Option(Text("nobody heard yet", style="grey50"), disabled=True))
            yield lst

    def on_mount(self) -> None:
        lst = self.query_one("#people", OptionList)
        if self.rows:
            lst.highlighted = 0
        lst.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id and event.option.id.startswith("p:"):
            self.dismiss(event.option.id[2:])

    def action_cancel(self) -> None:
        self.dismiss(None)


class SnippetEditScreen(ModalScreen[tuple]):
    """Add or change one saved line: a short key and the text (fields like {hops} allowed)."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, key: str = "", text: str = ""):
        super().__init__()
        self.key, self.text = key, text

    def compose(self) -> ComposeResult:
        with Vertical(id="snip_edit"):
            yield Label("Saved line" if self.key else "New saved line", classes="h")
            yield Label("Key, letters and digits (you type {{key}} or pick it from the list):")
            yield Input(value=self.key, placeholder="hop", max_length=16, id="snip_key")
            yield Label("Text; fields {hops} {via} {snr} {location} {time} {name} are filled in when you send:")
            yield Input(value=self.text, placeholder="{hops} {via} from {location}, hope the nodes are holding up",
                        max_length=200, id="snip_text")
            yield Label("", id="snip_msg")
            with Horizontal():
                yield Button("Save", variant="success", id="snip_save")
                yield Button("Cancel", id="snip_cancel")

    def on_mount(self) -> None:
        self.query_one("#snip_key" if not self.key else "#snip_text", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "snip_key":
            self.query_one("#snip_text", Input).focus()
        else:
            self.save()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "snip_save":
            self.save()
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def save(self) -> None:
        key = self.query_one("#snip_key", Input).value.strip()
        text = self.query_one("#snip_text", Input).value.strip()
        if not re.fullmatch(r"\w+", key):
            self.query_one("#snip_msg", Label).update("The key must be one word of letters and digits.")
            return
        if not text:
            self.query_one("#snip_msg", Label).update("Give the line a text.")
            return
        self.dismiss((key, text))


class SnippetScreen(ModalScreen[str]):
    """The window that opens on {{: your saved lines. Enter inserts one; they can be added, changed and deleted
    here and are kept in messages.json."""

    BINDINGS = [Binding("escape", "cancel", "Close"), Binding("n", "new", "New"), Binding("e", "edit", "Edit"),
                Binding("delete", "delete", "Delete")]

    def __init__(self, engine, preview):
        super().__init__()
        self.engine = engine
        self.preview = preview  # function(text) -> text with the fields filled in, for the list
        self.msg = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="snip_box"):
            yield Label("Saved lines, {{key}} in a message: Enter inserts, n new, e edit, Delete removes, Escape closes.")
            yield OptionList(id="snips")
            yield Label("", id="snip_status")
            with Horizontal():
                yield Button("Insert", variant="success", id="snip_insert")
                yield Button("New", id="snip_new")
                yield Button("Edit", id="snip_edit_btn")
                yield Button("Delete", id="snip_delete")
                yield Button("Close", id="snip_close")

    def on_mount(self) -> None:
        self.fill()
        self.query_one("#snips", OptionList).focus()

    def fill(self, select: str | None = None) -> None:
        lst = self.query_one("#snips", OptionList)
        lst.clear_options()
        snips = self.engine.msgs.get("snippets") or {}
        keys = list(snips)
        for key in keys:
            t = Text("{{%s}}" % key, style="bold #FFFF00")
            t.append("  " + snips[key][:60], style="#FFFFFF")
            try:
                shown = self.preview(snips[key])
            except Exception:
                shown = snips[key]
            if shown != snips[key]:
                t.append("  -> " + shown[:60], style="#80FF80")
            lst.add_option(Option(t, id="snip:" + key))
        if not keys:
            lst.add_option(Option(Text("no saved lines yet: press n or New", style="grey50"), disabled=True))
        elif select in keys:
            lst.highlighted = keys.index(select)
        else:
            lst.highlighted = 0
        self.query_one("#snip_status", Label).update(self.msg)

    def current_key(self) -> str | None:
        lst = self.query_one("#snips", OptionList)
        if lst.highlighted is None:
            return None
        opt = lst.get_option_at_index(lst.highlighted)
        return opt.id[5:] if opt.id and opt.id.startswith("snip:") else None

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id and event.option.id.startswith("snip:"):
            self.dismiss(event.option.id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        b = event.button.id
        if b == "snip_insert":
            key = self.current_key()
            if key:
                self.dismiss("snip:" + key)
        elif b == "snip_new":
            self.action_new()
        elif b == "snip_edit_btn":
            self.action_edit()
        elif b == "snip_delete":
            self.action_delete()
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_new(self) -> None:
        self.app.push_screen(SnippetEditScreen(), callback=lambda r: self.store(None, r))

    def action_edit(self) -> None:
        key = self.current_key()
        if key:
            self.app.push_screen(SnippetEditScreen(key, self.engine.msgs["snippets"][key]),
                                 callback=lambda r: self.store(key, r))

    def action_delete(self) -> None:
        key = self.current_key()
        if key:
            snips = dict(self.engine.msgs.get("snippets") or {})
            snips.pop(key, None)
            self.write(snips, "Removed {{%s}}." % key)
            self.fill()

    def store(self, old_key: str | None, result) -> None:
        if not result:
            self.query_one("#snips", OptionList).focus()
            return
        key, text = result
        snips = dict(self.engine.msgs.get("snippets") or {})
        if old_key and old_key != key:
            snips.pop(old_key, None)
        snips[key] = text
        self.write(snips, "Saved {{%s}}." % key)
        self.fill(key)
        self.query_one("#snips", OptionList).focus()

    def write(self, snips: dict, note: str) -> None:
        try:
            path = self.engine.save_snippets(snips)
            self.msg = "%s  (%s)" % (note, os.path.basename(path))
        except OSError as e:
            self.engine.msgs["snippets"] = snips
            self.msg = "%s  Could not write messages.json: %s" % (note, e)


class SendScreen(ModalScreen[dict]):
    """Operator's send window: pick where (channel, room or a person), type up to 140 characters, add an
    emoticon or a ready-made line. Returns {"target": value, "text": str} or None."""

    def __init__(self, targets: list, quick: list, emoticons: list, preset: str = "", preset_target=None):
        super().__init__()
        self.targets = targets          # [(label, value)]  value = ("chan", idx) | ("dm", key, name)
        self.quick = quick
        self.emoticons = emoticons
        self.preset = preset
        self.preset_target = preset_target

    def compose(self) -> ComposeResult:
        with Vertical(id="send_box"):
            yield Label("Send a message", classes="h")
            with Horizontal():
                yield Label("To: ")
                yield Select(self.targets, value=self.preset_target if self.preset_target is not None
                             else self.targets[0][1], allow_blank=False, id="send_target")
            yield Input(value=self.preset, placeholder="type here, Enter sends, Escape cancels", max_length=140,
                        id="send_text")
            yield Label("%d/140" % len(self.preset), id="send_count")
            with Horizontal(id="emo_row"):
                for i, e in enumerate(self.emoticons):
                    yield Button(e, id="emo%d" % i)
            yield Label("Ready-made lines (click one, then edit or send):", classes="h")
            yield OptionList(*self.quick, id="quick_list")
            yield Label("", id="send_msg")
            with Horizontal():
                yield Button("Send", variant="success", id="send")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#send_text", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "send_text":
            self.query_one("#send_count", Label).update("%d/140" % len(event.value))

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.do_send()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        inp = self.query_one("#send_text", Input)
        inp.value = str(event.option.prompt)[:140]
        inp.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("emo"):
            inp = self.query_one("#send_text", Input)
            add = self.emoticons[int(bid[3:])]
            sep = "" if not inp.value or inp.value.endswith(" ") else " "
            inp.value = (inp.value + sep + add)[:140]
            inp.focus()
        elif bid == "send":
            self.do_send()
        elif bid == "cancel":
            self.dismiss(None)

    def do_send(self):
        text = self.query_one("#send_text", Input).value.strip()
        if not text:
            self.query_one("#send_msg", Label).update("Nothing to send.")
            return
        self.dismiss({"target": self.query_one("#send_target", Select).value, "text": text})

    def key_escape(self) -> None:
        self.dismiss(None)


class RoomScreen(ModalScreen[dict]):
    """Create or join a room (a MeshCore channel) and invite people to it by direct message.
    Returns {"name", "secret", "invite": [(name, key)]} or None."""

    def __init__(self, engine, invite: dict | None = None):
        super().__init__()
        self.engine = engine
        self.found: list = []
        self.invite = invite  # {"name", "secret", "from"} when someone invited us

    def compose(self) -> ComposeResult:
        with Vertical(id="room_box"):
            yield Label("Chat room", classes="h")
            yield Label("Room name. With # it is a hashtag room: anyone who adds a channel with this exact "
                        "name is in. Without #, a private key is made and sent in the invite.")
            yield Input(value=self.invite["name"] if self.invite else "",
                        placeholder="#mytown   or   mygroup", id="room_name")
            yield Label("Invite (type part of a name, pick from the list; several allowed):", classes="h")
            yield Input(placeholder="search contacts", id="invite_search")
            yield OptionList(id="invite_list")
            yield Label("", id="invite_chosen")
            yield Label("", id="room_msg")
            with Horizontal():
                yield Button("Join room and send invites", variant="success", id="go")
                yield Button("Cancel", id="cancel")
        self.chosen: list = []

    def on_mount(self) -> None:
        self.fill("")
        if self.invite:
            self.query_one("#room_msg", Label).update(
                "%s invited you to %s: press the button to join." % (self.invite["from"], self.invite["name"]))
        elif not self.engine.contacts_loaded:
            self.query_one("#room_msg", Label).update(
                "Contacts not loaded yet (or none on the node): invites need the node's contact list.")

    def fill(self, q: str):
        lst = self.query_one("#invite_list", OptionList)
        lst.clear_options()
        self.found = self.engine.find_contacts(q, 10)
        for name, key in self.found:
            lst.add_option("%s  (%s)" % (name, key[:8]))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "invite_search":
            self.fill(event.value)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_index < len(self.found):
            pick = self.found[event.option_index]
            if pick not in self.chosen:
                self.chosen.append(pick)
            self.query_one("#invite_chosen", Label).update("Inviting: " + ", ".join(n for n, _ in self.chosen))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        name = self.query_one("#room_name", Input).value.strip()
        if not name:
            self.query_one("#room_msg", Label).update("Give the room a name.")
            return
        if self.invite and name == self.invite["name"]:
            secret = self.invite.get("secret")
        else:
            secret = None if name.startswith("#") else secrets.token_bytes(16)
        self.dismiss({"name": name, "secret": secret, "invite": list(self.chosen)})

    def key_escape(self) -> None:
        self.dismiss(None)


class RepeaterPasswordScreen(ModalScreen[tuple]):
    """Asks for the short name and the admin password of a repeater that becomes one of ours.
    Returns (name, password) or None."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, name: str, again: bool = False):
        super().__init__()
        self.rep_name = name
        self.again = again  # already ours: a new password replaces the saved one

    def compose(self) -> ComposeResult:
        with Vertical(id="pw_box"):
            yield Label("New password for %s (it replaces the saved one)" % self.rep_name if self.again
                        else "Make %s one of your repeaters" % self.rep_name, classes="h")
            yield Label("Short name on screen (five letters fit the panel):")
            yield Input(value=self.rep_name[:12], id="pw_name")
            yield Label("Its admin password, the one set in the MeshCore app's repeater settings. The repeater is "
                        "asked to accept it first; only then is it written to a file in the passwords folder next "
                        "to config.json, never into config.json itself.")
            yield Input(password=True, placeholder="admin password", id="pw_pass")
            yield Label("", id="pw_msg")
            with Horizontal():
                yield Button("Save and poll", variant="success", id="ok")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#pw_pass", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.ok()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            self.ok()
        else:
            self.dismiss(None)

    def ok(self) -> None:
        name = self.query_one("#pw_name", Input).value.strip()
        pw = self.query_one("#pw_pass", Input).value
        if not name or not pw.strip():
            self.query_one("#pw_msg", Label).update("Both the name and the password are needed.")
            return
        self.dismiss((name, pw))

    def action_cancel(self) -> None:
        self.dismiss(None)


class RepeaterScreen(ModalScreen[None]):
    """The repeater dialog: your own repeaters and every repeater in range, with how well each is heard.
    Enter polls one of yours or sends a signal test (a trace) to any other; m makes one yours (asks for its
    admin password); f forgets one of yours; t is a signal test for any row."""

    BINDINGS = [Binding("escape", "close", "Close"), Binding("m", "mine", "Make mine"),
                Binding("f", "forget", "Forget"), Binding("t", "test", "Signal test")]

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self.cands: list = []
        self.busy = False

    def compose(self) -> ComposeResult:
        with Vertical(id="rep_box"):
            yield Label("Repeaters: yours (mine) and the ones that carried packets to you in the last day", classes="h")
            yield Label("\"Mine\" is a repeater you own: you know its admin password. Any other repeater can only be "
                        "signal-tested. Enter polls one of yours (battery, status, neighbours) or sends a signal test "
                        "to any other: a trace that tells how well it hears you and you hear it. The row marked "
                        "\"closest\" is the one heard best, the natural one to test against. m makes the selected "
                        "repeater yours, or gives one of yours a new password: it is checked with the repeater "
                        "before anything is saved. f forgets one of yours, t is a signal test, Escape closes.")
            t = DataTable(id="rep_table", cursor_type="row", zebra_stripes=True)
            t.add_columns("", "Repeater", "Hash", "Pkts 24h", "SNR", "Heard", "Hops", "Dist", "Last result")
            yield t
            yield Label("", id="rep_msg")
            with Horizontal():
                yield Button("Poll or test (Enter)", variant="success", id="go")
                yield Button("Make mine (m)", id="mine")
                yield Button("Forget (f)", id="forget")
                yield Button("Close", id="close")

    def on_mount(self) -> None:
        self.fill()
        self.query_one("#rep_table", DataTable).focus()
        if not self.engine.mc:
            self.msg("Not connected to the node yet: the list comes from the log, polls and tests must wait.")
        elif not self.engine.contacts_loaded:
            self.msg("The node's contact list is not loaded yet: repeaters that sent no packet lately are missing.")

    def msg(self, text: str) -> None:
        self.query_one("#rep_msg", Label).update(text)

    @staticmethod
    def snr_style(snr) -> str:
        if snr is None:
            return "grey50"
        return "#00FF00" if snr >= 5 else "#FFFF00" if snr >= -5 else "#FF8000"

    def result_text(self, c: dict) -> Text:
        if c["mine"]:
            rep = self.engine.repeater_report(c["name"])
            if rep.get("ok"):
                t = Text("%.2fV" % ((rep.get("bat_mv") or 0) / 1000),
                         style=MeshOmitApp.battery_style(rep.get("percent")))
                if rep.get("percent") is not None:
                    t.append(" %d%%" % rep["percent"], style=MeshOmitApp.battery_style(rep.get("percent")))
                if rep.get("trace_there") is not None:
                    t.append(" trace %.1f/%.1f" % (rep["trace_there"], rep.get("trace_back") or 0), style="#00FFFF")
            elif rep.get("ts"):
                t = Text(rep.get("note") or "no answer", style="#FF8000")
            else:
                return Text("no poll yet", style="grey50")
            if rep.get("ts"):
                t.append(" " + time.strftime("%H:%M", time.localtime(rep["ts"])), style="grey42")
            return t
        r = self.engine.signal_tests.get(c["hash"][:4])
        if not r:
            return Text("")
        if r["ok"]:
            t = Text("hears you %+.1f" % (r["there"] or 0), style=self.snr_style(r["there"]))
            t.append(", you hear it %+.1f" % (r["back"] or 0), style=self.snr_style(r["back"]))
        else:
            t = Text("no answer", style="#FF8000")
        t.append(" " + time.strftime("%H:%M", time.localtime(r["ts"])), style="grey42")
        return t

    def fill(self) -> None:
        """Redraw the table from the engine's candidates, keeping the cursor where it was."""
        t = self.query_one("#rep_table", DataTable)
        row = t.cursor_row
        t.clear()
        self.cands = self.engine.repeater_candidates()
        now = time.time()
        for c in self.cands:
            mark = Text("mine", style="bold #FFD700") if c["mine"] else Text("")
            if c.get("closest"):
                mark.append(", " if c["mine"] else "", style="grey50")
                mark.append("closest", style="bold #00FFFF")
            name = Text(c["name"][:22], style="bold bright_white" if c["mine"] else "")
            snr = Text("" if c["snr"] is None else "%+.1f" % c["snr"], style=self.snr_style(c["snr"]))
            if c["last_heard"]:
                heard = Text(MeshOmitApp.ago(now - c["last_heard"]) + " ago", style="grey70")
            elif c["last_advert"]:
                heard = Text("advert " + MeshOmitApp.ago(max(0, now - c["last_advert"])) + " ago", style="grey50")
            else:
                heard = Text("not lately", style="grey42")
            hops = "" if c["hops"] is None else "direct" if c["hops"] == 0 else "%d" % c["hops"]
            dist = "" if c["km"] is None else "%.1f km %s" % (c["km"], c["dir"])
            t.add_row(mark, name, c["hash"].upper(), str(c["pkts"]) if c["pkts"] else "", snr, heard, hops, dist,
                      self.result_text(c), key=c["hash"])
        if self.cands:
            t.move_cursor(row=min(row if row is not None and row >= 0 else 0, len(self.cands) - 1))
        else:
            self.msg("Nothing heard yet and the node's contact list is empty or still loading. Leave the program "
                     "listening a few minutes, or make your repeater send an advert from its console, and open "
                     "this again.")

    def selected(self) -> dict | None:
        t = self.query_one("#rep_table", DataTable)
        i = t.cursor_row
        return self.cands[i] if self.cands and 0 <= i < len(self.cands) else None

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:  # Enter or a click on a row
        self.go()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "go":
            self.go()
        elif event.button.id == "mine":
            self.action_mine()
        elif event.button.id == "forget":
            self.action_forget()
        else:
            self.dismiss(None)

    def ready(self) -> bool:
        if self.busy:
            self.msg("Still working on the last one, a moment.")
            return False
        if not self.engine.mc:
            self.msg("Not connected to the node.")
            return False
        return True

    def go(self) -> None:
        c = self.selected()
        if not c or not self.ready():
            return
        if c["mine"]:
            rep = next((r for r in self.engine.cfg.get("repeaters", []) if r["name"] == c["name"]), None)
            if rep:
                self.run_worker(self.poll(rep), exclusive=True, group="rep")
        else:
            self.run_worker(self.test(c), exclusive=True, group="rep")

    def action_test(self) -> None:
        c = self.selected()
        if c and self.ready():
            self.run_worker(self.test(c), exclusive=True, group="rep")

    async def poll(self, rep: dict) -> None:
        if self.engine.polling:
            self.msg("The regular poll is running right now; try again in a minute.")
            return
        self.busy = True
        self.msg("Polling %s: trace, login, status, neighbours. This takes up to a minute..." % rep["name"])
        try:
            self.engine.polling = True
            try:
                await self.engine.poll_one(rep)
            finally:
                self.engine.polling = False
            self.app.show_repeaters(list(self.engine.repeater_rows.values()))
            rep_now = self.engine.repeater_report(rep["name"])
            if rep_now.get("ok"):
                self.msg("%s answered: %.2f V, up %.0f h, noise %s, trace %s/%s." % (
                    rep["name"], (rep_now.get("bat_mv") or 0) / 1000, (rep_now.get("uptime_s") or 0) / 3600,
                    rep_now.get("noise_floor"), rep_now.get("trace_there"), rep_now.get("trace_back")))
            else:
                self.msg("%s: %s. If the password changed, press m to give the new one (checked before it is "
                         "saved); f forgets the repeater." % (rep["name"], rep_now.get("note") or "no answer"))
        except Exception as e:
            self.msg("Poll failed: %s" % e)
        finally:
            self.busy = False
            self.fill()

    @staticmethod
    def quality(snr) -> str:
        return "solid" if snr >= 8 else "fine" if snr >= 0 else "weak but usable" if snr >= -8 else "at the edge"

    async def test(self, c: dict) -> None:
        if len(c["hash"]) < 4:
            self.msg("Only a one-byte hash is known for %s, too short for a trace." % c["name"])
            return
        self.busy = True
        self.msg("Signal test to %s: a trace goes out, the answer takes up to 6 seconds..." % c["name"])
        try:
            r = await self.engine.test_signal(c)
            if r["ok"]:
                self.msg("%s hears you at %+.1f dB (%s) and you hear it at %+.1f dB (%s)." % (
                    c["name"], r["there"] or 0, self.quality(r["there"] or 0), r["back"] or 0, self.quality(r["back"] or 0)))
            else:
                self.msg("No answer from %s. It may be out of reach right now or busy: try again, or test the "
                         "one marked closest." % c["name"])
        except Exception as e:
            self.msg("Signal test failed: %s" % e)
        finally:
            self.busy = False
            self.fill()

    def action_mine(self) -> None:
        c = self.selected()
        if not c:
            return
        if not c["key"]:
            self.msg("The node has no contact for this hash, so its full key is unknown. When its advert arrives, "
                     "/add it, then come back here.")
            return
        self.app.push_screen(RepeaterPasswordScreen(c["name"], again=c["mine"]), callback=lambda r: self.make_mine(c, r))

    def make_mine(self, c: dict, r) -> None:
        if not r:
            return
        name, pw = r
        if not self.ready():
            return
        self.run_worker(self.check_and_save(c, name, pw), exclusive=True, group="rep")

    async def check_and_save(self, c: dict, name: str, pw: str) -> None:
        """Log in to the repeater with the given password; save it as ours only when the repeater accepts it."""
        self.busy = True
        self.msg("Checking the password with %s (up to 30 seconds)..." % name)
        try:
            ok, why = await self.engine.login({"name": name, "pubkey": c["key"]}, pw)
        except Exception as e:
            ok, why = False, str(e)
        finally:
            self.busy = False
        if not ok:
            self.msg("%s did not accept it: %s. Nothing saved. Check the password in the MeshCore app's repeater "
                     "settings, and t for a signal test if it may be out of reach; then press m again." % (name, why))
            self.fill()
            return
        try:
            entry = self.engine.add_own_repeater(name, c["key"], pw)
        except OSError as e:
            self.msg("The password is right, but the file could not be written: %s" % e)
            return
        self.msg("%s accepted the password and is yours now (saved in %s). Polling it..."
                 % (name, entry["password_file"]))
        self.fill()
        self.run_worker(self.poll(entry), exclusive=True, group="rep")

    def action_forget(self) -> None:
        c = self.selected()
        if not c or not c["mine"]:
            self.msg("Select one of yours first.")
            return
        self.engine.forget_own_repeater(c["name"])
        self.app.show_repeaters(list(self.engine.repeater_rows.values()))
        self.fill()
        self.msg("%s is no longer polled. Its password file stays where it is." % c["name"])

    def action_close(self) -> None:
        self.dismiss(None)


class DashboardScreen(Screen):
    """Stats of the last 24 hours and the whole database. Toggled with d, closed with escape."""
    BINDINGS = [Binding("escape", "close", "Back"), Binding("d", "close", "Back")]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with VerticalScroll(id="dash"):
            with Horizontal(classes="cards"):
                yield Static("", id="card_heard", classes="card")
                yield Static("", id="card_tests", classes="card green")
                yield Static("", id="card_beacons", classes="card purple")
                yield Static("", id="card_repeaters", classes="card orange")
            with Horizontal(classes="spark_row"):
                with Vertical(classes="spark_box"):
                    yield Label("messages heard per hour, last 24 h")
                    yield Sparkline([0], id="sp_msgs")
                with Vertical(classes="spark_box"):
                    yield Label("tests heard per hour")
                    yield Sparkline([0], id="sp_tests")
                with Vertical(classes="spark_box"):
                    yield Label("our replies per hour")
                    yield Sparkline([0], id="sp_replies")
                with Vertical(classes="spark_box"):
                    yield Label("replies to our beacons per hour")
                    yield Sparkline([0], id="sp_beacon")
            with Horizontal(classes="tables"):
                yield DataTable(id="t_stations")
                yield DataTable(id="t_relays")
                yield DataTable(id="t_hops")
            with Horizontal(classes="tables"):
                yield DataTable(id="t_beacons")
                yield DataTable(id="t_repeaters")
            yield Static("", id="dash_replies")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = "Dashboard"
        for tid, title, cols in (
                ("t_stations", "Stations heard (24 h)", ("Station", "Msgs", "Hops", "Best SNR", "Last")),
                ("t_relays", "Heard via (24 h)", ("Repeater", "Packets", "%")),
                ("t_hops", "Hops away (24 h)", ("Hops", "Msgs", "")),
                ("t_beacons", "Last beacons", ("Time", "Replies", "Text")),
                ("t_repeaters", "Repeater polls", ("Rptr", "Time", "Batt", "Noise", "Trace", "State"))):
            t = self.query_one("#" + tid, DataTable)
            t.border_title = title
            t.add_columns(*cols)
            t.cursor_type = "none"
        self.query_one("#dash_replies", Static).border_title = "Our last answers"
        self.refresh_all()
        self.set_interval(30.0, self.refresh_all)

    def action_close(self) -> None:
        self.app.pop_screen()

    def refresh_all(self) -> None:
        app: "MeshOmitApp" = self.app  # type: ignore[assignment]
        db = app.db
        now = int(time.time())
        day = now - 24 * 3600
        s24 = db.stats(day)
        sall = db.stats(0)
        hourly = db.hourly(24)

        def card(wid, title, lines, color):
            txt = Text()
            txt.append(title + "\n", style="bold %s" % color)
            for label, val in lines:
                txt.append("%-14s" % label, style="#A0A0A0")
                txt.append("%s\n" % val, style="#FFFFFF")
            self.query_one("#" + wid, Static).update(txt)

        card("card_heard", "Heard", [("last 24 h", "%d msgs, %d stations" % (s24["messages"], s24["senders"])),
                                     ("all time", "%d msgs, %d stations" % (sall["messages"], sall["senders"])),
                                     ("busiest hour", "%d msgs" % max(hourly["messages"]))], "#00FFFF")
        rate24 = "%d%%" % (100 * s24["bot_replies"] / s24["triggers"]) if s24["triggers"] else "-"
        card("card_tests", "Tests", [("last 24 h", "%d heard, %d answered" % (s24["triggers"], s24["bot_replies"])),
                                     ("answer rate", rate24),
                                     ("all time", "%d heard, %d answered" % (sall["triggers"], sall["bot_replies"]))],
             "#00FF00")
        b24 = db.beacon_summary(day)
        ball = db.beacon_summary(0)
        hit = "%d%% got a reply" % (100 * b24[2] / b24[0]) if b24[0] else "-"
        card("card_beacons", "Beacons", [("last 24 h", "%d sent, %d replies" % (b24[0], b24[1])), ("hit rate", hit),
                                         ("all time", "%d sent, %d replies" % (ball[0], ball[1]))], "#C080FF")
        rep_lines = []
        cols = [d[0] for d in db.conn.execute("SELECT * FROM repeater_status LIMIT 0").description]
        for name in db.repeater_names():
            row = db.last_repeater_status(name)
            if row:
                r = dict(zip(cols, row))
                if r.get("ok"):
                    rep_lines.append((name, "%.2f V, noise %s" % ((r.get("bat_mv") or 0) / 1000, r.get("noise_floor"))))
                else:
                    rep_lines.append((name, r.get("note") or "no answer"))
        if not rep_lines:
            rep_lines = [("none", "no repeaters configured")]
        card("card_repeaters", "Repeaters", rep_lines, "#FF8000")

        self.query_one("#sp_msgs", Sparkline).data = hourly["messages"]
        self.query_one("#sp_tests", Sparkline).data = hourly["triggers"]
        self.query_one("#sp_replies", Sparkline).data = hourly["replies"]
        self.query_one("#sp_beacon", Sparkline).data = hourly["beacon_replies"]

        t = self.query_one("#t_stations", DataTable)
        t.clear()
        for sender, n, hops, snr, last in db.top_senders(day, 12):
            t.add_row(Text(sender[:22], style=nick_color(sender)), str(n),
                      "-" if hops is None else ("direct" if hops == 0 else str(hops)),
                      "-" if snr is None else "%+.1f" % snr, time.strftime("%H:%M", time.localtime(last)))
        t = self.query_one("#t_relays", DataTable)
        t.clear()
        relays = app.relays_by_name(db.relay_counts(day))
        total = sum(relays.values()) or 1
        for name, n in sorted(relays.items(), key=lambda kv: -kv[1])[:12]:
            t.add_row(name, str(n), "%d%%" % (100 * n / total))
        t = self.query_one("#t_hops", DataTable)
        t.clear()
        hist = db.hops_histogram(day)
        mx = max(hist.values()) if hist else 1
        for h, n in sorted(hist.items()):
            t.add_row("direct" if h == 0 else str(h), str(n), Text("#" * max(1, int(12 * n / mx)), style="#00FFFF"))
        t = self.query_one("#t_beacons", DataTable)
        t.clear()
        for ts, text, replies in db.beacon_history(10):
            t.add_row(time.strftime("%H:%M", time.localtime(ts)),
                      Text(str(replies), style="#00FF00" if replies else "#808080"), text[:48])
        t = self.query_one("#t_repeaters", DataTable)
        t.clear()
        for name in db.repeater_names():
            for ts, bat, noise, there, back, ok in db.repeater_history(name, 6):
                trace = "-" if there is None else "%.1f/%.1f" % (there, back or 0)
                t.add_row(name, time.strftime("%H:%M", time.localtime(ts)),
                          "-" if bat is None else "%.2f" % (bat / 1000), "-" if noise is None else str(noise), trace,
                          Text("ok", style="#00FF00") if ok else Text("miss", style="#FF5555"))
        txt = Text()
        for ts, to, text in db.recent_replies(8):
            txt.append(time.strftime("[%H:%M] ", time.localtime(ts)), style="#A0A0A0")
            txt.append("to %s: " % (to or "?"), style=nick_color(to or "?"))
            txt.append(text + "\n", style="#FFFFFF")
        if not txt:
            txt.append("no replies sent yet", style="#808080")
        self.query_one("#dash_replies", Static).update(txt)


class Ui:
    """Bridge from the engine to the widgets (same event loop, no threads)."""

    def __init__(self, app: "MeshOmitApp"):
        self.app = app

    def event(self, text, level="info"):
        self.app.show_event(text, level)

    def message(self, rec):
        self.app.show_message(rec)

    def status(self, d):
        self.app.show_status(d)

    def repeaters(self, rows):
        self.app.show_repeaters(rows)


ALL = ("all",)


class MeshOmitApp(App):
    CSS = CSS
    TITLE = "MeshOmit"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("m", "mode", "Bot/Operator"),
        Binding("enter", "send", "Send"),
        Binding("j", "room", "Room"),
        Binding("d", "dashboard", "Dashboard"),
        Binding("b", "beacon", "Beacon now"),
        Binding("t", "test", "Send Test"),
        Binding("r", "poll", "Poll repeaters"),
        Binding("p", "pause", "Pause/resume bot"),
        Binding("a", "reply", "Answer last test"),
        Binding("escape", "unfocus", "", show=False),
    ] + [Binding(str(i), "view(%d)" % i, "", show=False) for i in range(1, 10)]

    def __init__(self, cfg: dict | None, cfg_path: str):
        super().__init__()
        self.cfg = cfg
        self.cfg_path = cfg_path
        self.db = None
        self.engine = None
        self.asking_pin = False
        self.users: dict[str, dict] = {}   # nick -> {"ts", "hops", "snr", "count", "chans": {view: ts}}
        self.lines: list = []              # (view key, Text, rec) of everything shown, for switching windows
        self.view = ALL                    # ("all",) | ("chan", idx) | ("dm", key)
        self.views: list = [ALL]           # the windows, in list order
        self.view_names: dict = {ALL: "All"}
        self.unread: dict = {}
        self.last_test: dict | None = None      # the last test call heard, for the operator's reply
        self.last_from: dict[str, dict] = {}    # last message heard per sender
        self.picking = False                    # the field list is open

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield RichLog(id="conversation", wrap=True, markup=False, highlight=False)
                with Horizontal(id="sendbar"):
                    yield Label("", id="send_to")
                    yield Input(id="send_line", max_length=140, placeholder="type here, Enter sends")
            with Vertical(id="right"):
                yield Static("", id="status")
                yield OptionList(id="channels")
                yield OptionList(id="nicks")
                yield Static("", id="repeaters")
                yield RichLog(id="events", wrap=True, markup=False, highlight=False, min_width=10)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#status", Static).border_title = "Status"
        self.query_one("#channels", OptionList).border_title = "Windows (1-9)"
        self.query_one("#nicks", OptionList).border_title = "Nicks (last 3 h)"
        self.query_one("#events", RichLog).border_title = "Events"
        self.query_one("#repeaters", Static).border_title = "Repeaters"
        if self.cfg is None:
            self.write_system("*** First run: tell me how to reach your node.")
            self.run_worker(self.first_run(), exclusive=False, name="setup")
        else:
            self.start_engine()

    def on_unmount(self) -> None:
        if self.engine:
            self.engine.stop()
        if self.db is not None:
            self.db.close()
            self.db = None

    async def first_run(self):
        defaults = default_config(self.cfg_path)
        cfg = await self.push_screen_wait(SetupScreen(defaults))
        if not cfg:
            self.exit()
            return
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        self.write_system("*** Saved %s. Edit it any time for rules, repeaters and channels." % self.cfg_path)
        cfg["db"] = resolve_db(cfg, self.cfg_path)
        self.cfg = cfg
        self.start_engine()

    def start_engine(self):
        cfg = self.cfg
        self.db = Db(cfg.get("db", "meshomit.sqlite"))
        self.engine = Engine(cfg, self.db, Ui(self), self.cfg_path)
        self.engine.on_channels_changed = self.channels_changed
        self.rebuild_views()
        self.apply_mode()
        if self.engine.mode == "bot":
            self.write_system("*** MeshOmit started in Bot mode (start_mode in config.json): it answers tests and "
                              "beacons. Press m or type /op to take over.")
        else:
            self.write_system("*** MeshOmit started in Operator mode: you chat, the bot is off. Press m or type /bot "
                              "to let the bot answer tests and beacon.")
        self.write_system("*** Type in the box under this feed and press Enter: it goes to the window you are looking "
                          "at (a channel, a room or a <name> private window, which is encrypted). Empty Enter opens the "
                          "big send window with emoticons and quick texts; /help lists the commands.")
        self.write_system("*** Type @ in a message for the list of people heard lately: Enter puts @[name] in, "
                          "which their app shows as a mention.")
        self.write_system("*** Type { in a message for a list of fields: {hops} {via} {snr} {location} {time}... "
                          "They are filled in when you send, for the station you address with @[name]. "
                          "Type {{ for your saved lines (add and edit them there).")
        self.write_system("*** Keys when the box is not focused (press Escape): 1-9 window, a answer the last test "
                          "with hops and SNR, m mode, j room, d dashboard, b beacon, t test, r poll, q quit. "
                          "Click a nick or a <name> for a private window.")
        if not self.engine.cfg.get("repeaters"):
            self.write_system("*** Own a repeater? Click the Repeaters panel (or type /repeaters) once connected: "
                              "pick it from the list, press m and give its admin password. It is checked with the "
                              "repeater, then watched every half hour: battery, noise, trace, neighbours.")
        self.update_sendbar()
        self.query_one("#send_line", Input).focus()
        self.write_system("*** Texts come from %s" % os.path.basename(self.engine.msgs.get("_path", "messages.json")))
        self.run_worker(self.engine.run(), exclusive=False, name="engine")
        self.set_interval(1.0, self.poll_pin)
        self.show_repeaters([])
        self.set_interval(30.0, self.refresh_nicks)

    # ---- windows (channels, rooms, private chats) ----
    def rebuild_views(self):
        """One window per channel the node listens to, plus the private windows already open."""
        chans = [("chan", idx) for idx in sorted(self.engine.channels)]
        dms = [v for v in self.views if v[0] == "dm"]
        self.views = [ALL] + chans + dms
        for idx in self.engine.channels:
            self.view_names[("chan", idx)] = self.engine.channels[idx]
        if self.view not in self.views:
            self.view = ALL
        self.refresh_channels()

    @staticmethod
    def view_of(rec: dict):
        if rec.get("kind") in ("dm", "dm_tx"):
            return ("dm", rec.get("dm_key") or "")
        return ("chan", rec.get("channel_idx"))

    def view_label(self, vk) -> Text:
        name = self.view_names.get(vk, "?")
        t = Text()
        if vk == ALL:
            t.append("All", style="bold #FFFFFF" if self.view == vk else "#FFFFFF")
        elif vk[0] == "chan":
            t.append(name, style=("bold " if self.view == vk else "") + CHANNEL_COLORS.get(name, "#BBBBBB"))
            room = self.engine.rooms.get(name) if self.engine else None
            if room and room.get("creator"):
                t.append("  *%s" % room["creator"], style="#FFD700")
        else:
            t.append("-> " + name, style=("bold " if self.view == vk else "") + "#C8A2C8")
        n = self.unread.get(vk, 0)
        if n:
            t.append("  (%d)" % n, style="bold #FFFF00")
        return t

    def refresh_channels(self):
        lst = self.query_one("#channels", OptionList)
        lst.clear_options()
        for i, vk in enumerate(self.views):
            label = Text("%d " % (i + 1) if i < 9 else "  ", style="#8A8A8A")
            label.append_text(self.view_label(vk))
            lst.add_option(label)
        try:
            lst.highlighted = self.views.index(self.view)
        except ValueError:
            pass

    def select_view(self, vk):
        if vk not in self.views:
            return
        self.view = vk
        self.unread[vk] = 0
        log = self.query_one("#conversation", RichLog)
        log.clear()
        for k, line, rec in self.lines:
            if vk == ALL or k == vk:
                log.write(line)
        name = self.view_names.get(vk, "?")
        if vk == ALL:
            log.border_title = ", ".join(self.engine.channels.values()) if self.engine else "All"
        elif vk[0] == "dm":
            log.border_title = "private: %s" % name
        else:
            room = self.engine.rooms.get(name) if self.engine else None
            log.border_title = name + ("  (room by %s)" % room["creator"] if room and room.get("creator") else "")
        self.refresh_channels()
        self.refresh_nicks()
        self.update_sendbar()

    def update_sendbar(self):
        """The label in front of the input line names where Enter sends to."""
        lab = self.query_one("#send_to", Label)
        inp = self.query_one("#send_line", Input)
        if not self.engine:
            lab.update("")
            return
        t = self.current_target()
        if t[0] == "dm":
            lab.update(Text("<%s>" % t[2], style="bold"))
            inp.placeholder = "private (encrypted) message to %s, Enter sends" % t[2]
        else:
            name = self.engine.channels.get(t[1], "?")
            lab.update(Text(("All -> " if self.view == ALL else "") + name, style="bold"))
            inp.placeholder = "message to %s, Enter sends, /help for commands" % name

    def action_unfocus(self):
        self.set_focus(None)

    def focus_line(self):
        try:
            self.query_one("#send_line", Input).focus()
        except Exception:
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "send_line" or not self.engine:
            return
        text = event.value.strip()
        event.input.value = ""
        if not text:
            self.run_worker(self.send_dialog("", self.current_target()), exclusive=False, name="send")
        elif text.startswith("/"):
            await self.command(text)
        else:
            await self.send_to_target(self.current_target(), text)

    def action_reply(self):
        if self.engine and not isinstance(self.screen, ModalScreen):
            self.prepare_reply("")

    def prepare_reply(self, name: str = ""):
        """Put a factual answer in the input line: to the last test call heard, or to the last message of
        the named station. The operator reads it, edits it and presses Enter."""
        if name:
            hits = [n for n in self.last_from if n.lower() == name.lower()] or \
                   [n for n in self.last_from if name.lower() in n.lower()]
            rec = self.last_from.get(hits[0]) if hits else None
            if rec is None:
                self.write_system("*** Nothing heard from %s since the start." % name)
                return
        else:
            rec = self.last_test
            if rec is None:
                self.write_system("*** No test call heard since the start. /reply NAME answers that station's last line.")
                return
        vk = self.view_of(rec)
        if vk in self.views and self.view != vk:
            self.select_view(vk)
        inp = self.query_one("#send_line", Input)
        inp.value = self.engine.operator_reply(rec)
        inp.cursor_position = len(inp.value)
        inp.focus()
        when = time.strftime("%H:%M", time.localtime(rec.get("ts", time.time())))
        self.write_system("*** Answer to %s (%s, %s) ready in the input line: edit it, Enter sends, Escape and "
                          "Ctrl+U clear it." % (rec.get("sender"), when, rec.get("channel_name")))

    async def cmd_add(self, arg: str):
        if not arg:
            rows = self.engine.pending_adverts()
            if not rows:
                self.write_system("*** No advert waiting. Ask the person to press Advert in their app; it shows up "
                                  "here within seconds%s." % ("" if self.engine.manual_contacts else
                                                               " (automatic mode: the node adds them by itself)"))
                return
            self.write_system("*** Adverts waiting, /add NAME keeps one (%d):" % len(rows))
            for c in rows[:20]:
                kind = self.engine.CONTACT_TYPES.get(c.get("type"), "node")
                when = c.get("seen") or c.get("last_advert")
                hops = c.get("out_path_len")
                self.write_system("      %-24s %-10s %s%s" % (
                    self.engine.advert_name(c)[:24], kind,
                    time.strftime("%H:%M", time.localtime(when)) if when else "?",
                    "" if hops is None or hops < 0 else ("  direct" if hops == 0 else "  %d hops" % hops)))
            return
        self.write_system("*** " + await self.engine.add_contact(arg))
        self.refresh_nicks()
        self.update_sendbar()

    async def cmd_contacts(self, arg: str):
        words = arg.split()
        sub = words[0].lower() if words else ""
        eng = self.engine
        if sub == "":
            n = len(eng.mc.contacts) if eng.mc else 0
            self.write_system("*** Contacts: %d on the node, %d in contacts.json (yours), %d adverts waiting; %s mode. "
                              "/contacts export | clear yes | restore | manual on|off" % (
                                  n, len(eng.my_contacts()), len(eng.pending_adverts()),
                                  "manual" if eng.manual_contacts else "automatic"))
        elif sub == "export":
            try:
                path, n = await eng.export_contacts()
                self.write_system("*** %d contacts written to %s" % (n, path))
            except Exception as e:
                self.write_system("*** Export failed: %s" % e)
        elif sub == "clear":
            if len(words) < 2 or words[1].lower() != "yes":
                self.write_system("*** This removes every contact from the node (a backup file is written first). "
                                  "Type /contacts clear yes to do it.")
                return
            self.write_system("*** Clearing the node's contact list, this takes a while over Bluetooth...")
            self.write_system("*** " + await eng.clear_contacts(lambda t: self.write_system("*** " + t)))
            self.refresh_nicks()
        elif sub == "restore":
            self.write_system("*** " + await eng.restore_contacts(lambda t: self.write_system("*** " + t)))
        elif sub == "manual":
            on = len(words) < 2 or words[1].lower() in ("on", "yes", "1", "true")
            self.write_system("*** Contacts " + await eng.set_manual(on))
            self.save_config_key("contacts", {"manual": on})
        else:
            self.write_system("*** /contacts, /contacts export, /contacts clear yes, /contacts restore, "
                              "/contacts manual on|off")

    def save_config_key(self, key: str, value) -> None:
        try:
            with open(self.cfg_path, encoding="utf-8-sig") as f:
                on_disk = json.load(f)
            on_disk[key] = value
            with open(self.cfg_path, "w", encoding="utf-8") as f:
                json.dump(on_disk, f, indent=2)
        except (OSError, ValueError):
            pass

    def whois(self, name: str):
        """Type, last advert, position (with a map link) and distance of a contact, from the node's list."""
        info = self.engine.contact_info(name)
        if not info:
            self.write_system("*** %s is not in the node's contact list%s." % (
                name, "" if self.engine.contacts_loaded else " (the list is still loading)"))
            return
        line = Text(time.strftime("[%H:%M] "), style="#A0A0A0")
        line.append("*** %s: %s" % (info["name"], info["type"]), style="#00FF00")
        if info["last_advert"]:
            ago = int(time.time()) - int(info["last_advert"])
            when = "%d min" % (ago // 60) if ago < 3600 else "%.1f h" % (ago / 3600) if ago < 86400 else "%.1f d" % (ago / 86400)
            line.append(", last advert %s ago" % when, style="#00FF00")
        if info["path_len"] is not None and 0 <= info["path_len"] < 64:
            line.append(", %s" % ("direct" if info["path_len"] == 0 else "%d hops" % info["path_len"]), style="#00FF00")
        if info["lat"] is None:
            line.append(". No position in its advert (the owner has not set one).", style="#00FF00")
        else:
            line.append(", at %.4f, %.4f" % (info["lat"], info["lon"]), style="#00FF00")
            if info["km"] is not None:
                line.append(" (%.1f km %s of %s)" % (info["km"], info["dir"], self.engine.node_name), style="#00FF00")
            url = "https://www.openstreetmap.org/?mlat=%.5f&mlon=%.5f&zoom=13" % (info["lat"], info["lon"])
            line.append("  map: ", style="#00FF00")
            line.append(url, style="underline #80C0FF link " + url)
            if info["km"] is None:
                line.append("  (set a position on your own node to see distances)", style="#8A8A8A")
        self.query_one("#conversation", RichLog).write(line)

    def addressed_record(self, text: str) -> dict | None:
        """The message the fields refer to: the last one from the station named with @[...] at the start of
        the text, else the last message received in the window being looked at, else the last test call."""
        m = re.match(r"\s*@\[([^\]]+)\]", text or "")
        if m:
            want = m.group(1).strip().lower()
            for n, rec in self.last_from.items():
                if n.lower() == want:
                    return rec
        for vk, _, rec in reversed(self.lines):
            if rec and rec.get("kind") in ("rx", "beacon_reply", "dm") and (self.view == ALL or vk == self.view):
                return rec
        return self.last_test

    def field_values(self, text: str) -> dict:
        rec = self.addressed_record(text) or {}
        hops = rec.get("hops")
        names = [n for n in (rec.get("path_names") or []) if n]
        cfg = self.engine.cfg if self.engine else {}
        return {
            "name": rec.get("sender", "?"),
            "hops": self.engine.hops_words(hops) if self.engine else "?",
            "via": ("via " + ">".join(names[-4:])) if names else ("direct" if hops == 0 else "?"),
            "snr": "?" if rec.get("snr") is None else "%+.1f" % rec["snr"],
            "rssi": "?" if rec.get("rssi") is None else "%.0f" % rec["rssi"],
            "heard": time.strftime("%H:%M", time.localtime(rec["ts"])) if rec.get("ts") else "?",
            "location": cfg.get("operator_location") or (cfg.get("locations") or ["here"])[0],
            "time": time.strftime("%H:%M"),
            "me": self.engine.node_name if self.engine else "?",
        }

    def expand_fields(self, text: str) -> str:
        """Replace {{key}} with the saved line, then {hops}, {via}, {snr}... with their values. Unknown names
        are left as typed."""
        if "{" not in text:
            return text
        snips = (self.engine.msgs.get("snippets") if self.engine else None) or {}
        text = re.sub(r"\{\{(\w+)\}\}", lambda m: snips.get(m.group(1), m.group(0)), text)
        values = self.field_values(text)
        return re.sub(r"(?<!\{)\{(\w+)\}(?!\})", lambda m: str(values.get(m.group(1), m.group(0))), text)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id not in ("send_line", "send_text") or self.picking or not self.engine:
            return
        value = event.value
        at = value.rfind("@")
        if at >= 0 and at in (len(value) - 1, event.input.cursor_position - 1) and (at == 0 or value[at - 1] == " ") \
                and not value[at + 1:at + 2] == "[":
            self.picking = True
            self.run_worker(self.pick_person(event.input, at), exclusive=False, name="people")
            return
        idx = value.rfind("{")
        pos = event.input.cursor_position
        # a { just typed (at the end, or at the cursor), not a {{ and not an already closed {field}
        if idx >= 0 and idx in (len(value) - 1, pos - 1, pos) and "}" not in value[idx:]                 and not (idx > 0 and value[idx - 1] == "{"):
            self.picking = True
            self.run_worker(self.pick_field(event.input, idx), exclusive=False, name="fields")

    def people_rows(self) -> list:
        """Who was heard in the last 3 hours: the current window's stations first, then the rest, newest first."""
        now = time.time()
        keys = set(self.engine.mc.contacts) if self.engine and self.engine.mc else set()
        names_of_contacts = {(c.get("adv_name") or "") for k, c in (self.engine.mc.contacts.items()
                                                                   if self.engine and self.engine.mc else [])}
        rows = []
        for n, u in self.users.items():
            ts = u.get("ts", 0)
            if not ts or now - ts > 3 * 3600 or (self.engine and n == self.engine.node_name):
                continue
            here = self.view == ALL or bool(u.get("chans", {}).get(self.view))
            rec = self.last_from.get(n) or {}
            rows.append((n, rec.get("channel_name") or "", u.get("hops"), int(now - ts), n in names_of_contacts, here))
        rows.sort(key=lambda r: (not r[5], r[3]))
        return rows[:40] if keys or rows else rows

    async def pick_person(self, inp: Input, at: int):
        try:
            name = await self.push_screen_wait(PeopleScreen(self.people_rows()))
        finally:
            self.picking = False
        if name and inp.value[at:at + 1] == "@":
            ins = "@[%s] " % name
            inp.value = inp.value[:at] + ins + inp.value[at + 1:]
            inp.cursor_position = at + len(ins)
        inp.focus()

    async def pick_field(self, inp: Input, idx: int):
        try:
            picked = await self.push_screen_wait(FieldScreen(self.field_values(inp.value),
                                                             self.engine.msgs.get("emoticons", [])))
        finally:
            self.picking = False
        if picked == "snippets":  # { typed twice: the saved lines
            self.picking = True
            try:
                picked = await self.push_screen_wait(SnippetScreen(self.engine, self.expand_fields))
            finally:
                self.picking = False
        if picked and inp.value[idx:idx + 1] == "{":
            kind, _, what = picked.partition(":")
            if kind == "field":
                ins = "{%s}" % what
            elif kind == "snip":
                ins = (self.engine.msgs.get("snippets") or {}).get(what, "") + " "
            else:
                ins = what + " "  # an emoticon replaces the brace
            inp.value = inp.value[:idx] + ins + inp.value[idx + 1:]
            inp.cursor_position = idx + len(ins)
        inp.focus()

    async def send_to_target(self, target, text: str):
        if not self.engine.mc:
            self.write_system("*** Not connected to the node yet.")
            return
        text = self.expand_fields(text)
        if target[0] == "chan":
            await self.engine.send_channel(target[1], text, kind="tx")
        else:
            await self.engine.send_dm(target[1], target[2], text)

    async def command(self, line: str):
        """IRC-style slash commands typed in the input line."""
        parts = line[1:].split(None, 1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1].strip() if len(parts) > 1 else ""
        if cmd in ("help", "?"):
            self.write_system("*** Commands: /reply [NAME] (answer the last test, or NAME's last message, with hops "
                              "and SNR)  /repeaters (the repeater dialog: poll yours, signal-test any, make one yours; "
                              "/repeaters report prints the text report)  "
                              "/add [NAME] (adverts waiting, or add one as a contact)  /forget NAME  "
                              "/contacts [export|clear yes|restore|manual on|off]  "
                              "/bot /op (bot on/off)  /w N (window N)  /query NAME (private window)  "
                              "/msg NAME TEXT  /whois NAME (type, last advert, position, distance)  /join (room)  "
                              "/send (big window)  /dash  /beacon  /test  /poll  /pause  /quit")
        elif cmd in ("whois", "who", "where", "loc") and arg:
            self.whois(arg)
        elif cmd in ("reply", "re", "answer"):
            self.prepare_reply(arg)
        elif cmd in ("repeaters", "rep", "rptr"):
            if arg.lower() in ("report", "text", "list"):
                self.repeaters_report()
            else:
                self.open_repeaters()
        elif cmd == "add":
            await self.cmd_add(arg)
        elif cmd == "forget" and arg:
            self.write_system("*** " + await self.engine.forget_contact(arg))
            self.refresh_nicks()
        elif cmd == "contacts":
            await self.cmd_contacts(arg)
        elif cmd in ("bot", "op", "operator"):
            want = "bot" if cmd == "bot" else "operator"
            if self.engine.mode != want:
                self.action_mode()
            else:
                self.write_system("*** Already in %s mode." % want)
        elif cmd == "mode":
            self.action_mode()
        elif cmd in ("w", "win", "window") and arg.isdigit():
            self.action_view(int(arg))
        elif cmd.isdigit():
            self.action_view(int(cmd))
        elif cmd in ("query", "q", "pm") and arg:
            self.open_private(arg)
        elif cmd == "msg" and arg:
            words = arg.split()
            for i in range(len(words) - 1, 0, -1):  # the longest leading words that name a contact exactly
                name = " ".join(words[:i])
                hit = [h for h in self.engine.find_contacts(name, 10) if h[0].lower() == name.lower()]
                if hit:
                    await self.send_to_target(("dm", hit[0][1], hit[0][0]), " ".join(words[i:]))
                    break
            else:
                self.write_system("*** /msg NAME TEXT: no contact named like that (names are matched whole).")
        elif cmd in ("join", "j"):
            await self.action_room()
        elif cmd in ("send", "s"):
            self.run_worker(self.send_dialog("", self.current_target()), exclusive=False, name="send")
        elif cmd in ("dash", "d"):
            self.action_dashboard()
        elif cmd in ("beacon", "b"):
            await self.action_beacon()
        elif cmd in ("test", "t"):
            await self.action_test()
        elif cmd in ("poll", "r"):
            await self.action_poll()
        elif cmd in ("pause", "p"):
            self.action_pause()
        elif cmd in ("quit", "exit"):
            await self.action_quit()
        else:
            self.write_system("*** Unknown command /%s, try /help" % cmd)

    def action_view(self, n: int):
        if 1 <= n <= len(self.views):
            self.select_view(self.views[n - 1])

    def open_private(self, nick: str):
        """A private window with a contact of the node (like a query window)."""
        if not self.engine or nick == self.engine.node_name:
            return
        key = ""
        for name, k in self.engine.find_contacts(nick, 50):
            if name == nick:
                key = k
                break
        if not key:
            self.write_system("*** %s is not in the node's contact list, so no private message is possible." % nick)
            return
        vk = ("dm", key)
        if vk not in self.views:
            self.views.append(vk)
            self.view_names[vk] = nick
        self.select_view(vk)
        self.query_one("#send_line", Input).focus()

    @staticmethod
    def nick_style(nick: str, style: str, chan=None) -> Style:
        """Nick colour plus a click action: a name in the feed lights up under the mouse and opens a message."""
        return Style.parse(style) + Style.from_meta({"@click": "app.nick_click(%r, %r)" % (nick, chan)})

    def action_nick_click(self, nick: str, chan=None):
        """Mouse click on a name in the feed: private window when the node knows the contact, else a mention
        on the channel the message came from."""
        if not self.engine or nick == self.engine.node_name or isinstance(self.screen, ModalScreen):
            return
        if any(name == nick for name, _ in self.engine.find_contacts(nick, 50)):
            self.open_private(nick)
            return
        if chan is not None and ("chan", chan) in self.views:
            self.select_view(("chan", chan))
        inp = self.query_one("#send_line", Input)
        inp.value = "@[%s] " % nick
        inp.cursor_position = len(inp.value)
        inp.focus()
        self.write_system("*** %s is not in the node's contact list, so no private message is possible: "
                          "a mention is typed for you instead." % nick)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "channels":
            if event.option_index < len(self.views):
                self.select_view(self.views[event.option_index])
        elif event.option_list.id == "nicks":
            nick = getattr(event.option, "nick", None) or str(event.option.prompt).lstrip("*").split(" ")[0]
            self.open_private(nick)

    # ---- conversation feed ----
    def write_system(self, text: str):
        line = Text(time.strftime("[%H:%M] "), style="#A0A0A0")
        line.append(text, style="#00FF00")
        self.query_one("#conversation", RichLog).write(line)

    def show_message(self, rec: dict):
        kind = rec.get("kind", "rx")
        me = self.engine.node_name if self.engine else "?"
        line = Text(time.strftime("[%H:%M] ", time.localtime(rec.get("ts", time.time()))), style="#A0A0A0")
        chan = rec.get("channel_name") or ""
        line.append("%-6s " % chan[:6], style=CHANNEL_COLORS.get(chan, "#C8A2C8" if chan == "DM" else "grey62"))
        sender = rec.get("sender") or "?"
        text = rec.get("text") or ""
        mentioned = ("@[%s]" % me).lower() in text.lower() or me.lower() in text.lower()
        hops = rec.get("hops")
        dim = kind == "backlog"

        if kind == "beacon":
            line.append("* %s %s" % (me, text), style="#C080FF")
        elif kind == "dm_tx":
            line.append("-> %s: " % rec.get("to", "?"), style="bold #C8A2C8")
            line.append(text, style="#C8A2C8")
        elif kind == "dm":
            line.append("<%s>" % sender, style=self.nick_style(sender, "bold " + nick_color(sender)))
            line.append(" ")
            line.append(text, style="black on #C8A2C8")
            if rec.get("snr") is not None:
                line.append(" (%+.1fdB)" % rec["snr"], style="#8A8A8A")
        elif kind in ("bot_reply", "tx"):
            line.append("<%s> " % me, style="bold bright_white")
            line.append(text, style="bright_white")
        else:
            color = nick_color(sender)
            if rec.get("is_trigger"):
                line.append("<%s>" % sender, style=self.nick_style(sender, "bold " + color, rec.get("channel_idx")))
                line.append(" ")
                line.append(text, style="bold #FFFF00")
            elif mentioned or kind == "beacon_reply":
                line.append("<%s>" % sender, style=self.nick_style(sender, "bold " + color, rec.get("channel_idx")))
                line.append(" ")
                line.append(text, style="black on #FFFF00")
            else:
                line.append("<%s>" % sender, style=self.nick_style(sender, ("dim " if dim else "bold ") + color, rec.get("channel_idx")))
                line.append(" ")
                line.append(text, style="#888888" if dim else "#FFFFFF")
            if hops is not None and not dim:
                extra = " (%s" % ("direct" if hops == 0 else "%dh" % hops)
                if rec.get("snr") is not None:
                    extra += " %+.1fdB" % rec["snr"]
                names = rec.get("path_names") or []
                if names:
                    extra += " via " + ">".join(names[-3:])
                extra += ")"
                line.append(extra, style="#8A8A8A")

        if kind in ("rx", "beacon_reply") and sender != "?":
            self.last_from[sender] = rec
            if rec.get("is_trigger"):
                self.last_test = rec
        vk = self.view_of(rec)
        if vk[0] == "dm" and vk not in self.views:  # a new private window opens by itself
            self.views.append(vk)
            self.view_names[vk] = rec.get("to") if kind == "dm_tx" else sender
            self.refresh_channels()
        if kind in ("rx", "backlog", "beacon_reply", "dm") and sender != "?":
            # backlog lines count too, at the time they were sent, so the nick list is not empty at startup
            seen_at = rec.get("sender_ts") if dim and rec.get("sender_ts") else rec.get("ts", time.time())
            u = self.users.setdefault(sender, {"count": 0, "ts": 0, "chans": {}})
            if seen_at >= u["ts"]:
                u.update({"ts": seen_at, "hops": hops, "snr": rec.get("snr")})
            u["count"] += 1
            u["chans"][vk] = max(u["chans"].get(vk, 0), seen_at)
        self.lines.append((vk, line, rec))
        if len(self.lines) > 4000:
            del self.lines[:500]
        if self.view == ALL or self.view == vk:
            self.query_one("#conversation", RichLog).write(line)
            self.refresh_nicks()
        else:
            self.unread[vk] = self.unread.get(vk, 0) + 1
            self.refresh_channels()
        if kind == "dm" and self.engine and self.engine.pending_invite \
                and self.engine.pending_invite.get("from") == sender:
            inv = self.engine.pending_invite
            self.write_system("*** %s invites you to %s. Press j to join." % (sender, inv["name"]))

    def refresh_nicks(self):
        now = time.time()
        vk = self.view
        rows = []
        for n, u in self.users.items():
            ts = u.get("ts", 0) if vk == ALL else u.get("chans", {}).get(vk, 0)
            if ts and now - ts < 3 * 3600:
                rows.append((n, u, ts))
        rows.sort(key=lambda r: -r[2])
        lst = self.query_one("#nicks", OptionList)
        lst.clear_options()
        creator = None
        if vk != ALL and vk[0] == "chan" and self.engine:
            room = self.engine.rooms.get(self.view_names.get(vk, ""))
            creator = room.get("creator") if room else None
        if creator:
            t = Text("*%s" % creator, style="bold #FFD700")
            t.append("  room creator", style="grey50")
            opt = Option(t)
            opt.nick = creator
            lst.add_option(opt)
        for n, u, ts in rows[:12]:
            if n == creator:
                continue
            hops = u.get("hops")
            tag = "" if hops is None else (" direct" if hops == 0 else " %dh" % hops)
            info = self.engine.contact_info(n) if self.engine and self.engine.contacts_loaded else None
            if info and info.get("km") is not None:
                tag += " %.0fkm %s" % (info["km"], info["dir"]) if info["km"] >= 10 else " %.1fkm %s" % (info["km"], info["dir"])
            t = Text("%-16s" % n[:16], style=nick_color(n))
            t.append("%s x%d" % (tag, u.get("count", 1)), style="grey50")
            opt = Option(t)
            opt.nick = n
            lst.add_option(opt)
        if not rows and not creator:
            lst.add_option(Option(Text("nobody yet", style="grey42"), disabled=True))

    # ---- other panels ----
    def show_event(self, text: str, level: str):
        color = {"ok": "bright_green", "warn": "yellow", "error": "bright_red"}.get(level, "grey70")
        line = Text(time.strftime("%H:%M:%S "), style="grey50")
        line.append(text, style=color)
        self.query_one("#events", RichLog).write(line)
        if level == "warn":
            self.write_system("*** " + text)

    def show_status(self, d: dict):
        c = d.get("counters", {})
        now = time.time()

        def mmss(t):
            if not t:
                return "-"
            s = max(0, int(t - now))
            return "%d:%02d" % (s // 60, s % 60)

        def since(t):
            if not t:
                return "-"
            s = int(now - t)
            return "%dh%02dm" % (s // 3600, (s % 3600) // 60)

        state = d.get("state", "")
        state_style = {"listening": "bold bright_green", "connecting": "yellow", "reconnecting": "yellow",
                       "need PIN": "bold bright_red", "starting": "grey70"}.get(state, "grey70")
        txt = Text()
        txt.append("%s " % d.get("node", "?"), style="bold bright_white"); txt.append(state, style=state_style)
        txt.append("  link %s\n" % since(d.get("since")), style="grey50")
        txt.append("%s\n" % d.get("address", ""), style="grey42")
        if d.get("mode") == "operator":
            txt.append("OPERATOR mode: you talk, bot silent\n", style="bold #C8A2C8")
        else:
            txt.append("BOT mode: ", style="bold bright_green")
            txt.append("paused\n" if d.get("bot_paused") else "answering tests, beacons on\n",
                       style="bright_red" if d.get("bot_paused") else "bright_green")
        if d.get("contacts"):
            txt.append("%d contacts on the node\n" % d["contacts"], style="grey50")
        txt.append("heard %d msgs, %d tests, answered %d\n" % (
            c.get("messages", 0), c.get("triggers", 0), c.get("replies", 0)), style="#d0d0d0")
        txt.append("beacons %d sent, %d replies, next %s\n" % (
            c.get("beacons", 0), c.get("beacon_replies", 0), mmss(d.get("next_beacon"))), style="medium_purple1")
        txt.append("repeater poll in %s\n" % mmss(d.get("next_poll")), style="grey70")
        relays = self.relays_by_name(d.get("relays_1h") or {})
        if relays:
            parts = ["%s %d" % (name, n) for name, n in sorted(relays.items(), key=lambda kv: -kv[1])[:4]]
            txt.append("heard via " + ", ".join(parts) + " (1h)", style="grey50")
        self.query_one("#status", Static).update(txt)

    def relays_by_name(self, counts: dict) -> dict:
        """Packet counts per last hop, merged by repeater name: the 1-byte and 2-byte hash forms of the same
        repeater are one entry, unknown hashes stay as they are, '' is 'direct'."""
        out: dict = {}
        for h, n in counts.items():
            name = (self.engine.hop_name(h) if self.engine else h) if h else "direct"
            out[name] = out.get(name, 0) + n
        return out

    @staticmethod
    def battery_style(pct) -> str:
        return "#00FF00" if pct is None or pct >= 50 else "#FFFF00" if pct >= 25 else "bold #FF4040"

    @staticmethod
    def ago(secs) -> str:
        if secs is None:
            return "?"
        return "%ds" % secs if secs < 60 else "%dm" % (secs // 60) if secs < 3600 else "%.1fh" % (secs / 3600)

    def show_repeaters(self, rows: list):
        """Two lines per repeater: battery (with a rough percentage and the day's drain), uptime, noise and
        trace; then the strongest neighbour that is not one of ours."""
        if not self.engine:
            return
        names = [r["name"] for r in self.engine.cfg.get("repeaters", [])] or [r["name"] for r in rows]
        txt = Text()
        for name in names:
            rep = self.engine.repeater_report(name)
            txt.append("%-5s" % name[:5], style="bold bright_white")
            if rep.get("ok"):
                pct = rep.get("percent")
                txt.append(" %.2fV" % ((rep.get("bat_mv") or 0) / 1000), style=self.battery_style(pct))
                if pct is not None:
                    txt.append(" %d%%" % pct, style=self.battery_style(pct))
                if rep.get("mv_per_day") is not None:
                    txt.append(" %+dmV/d" % -round(rep["mv_per_day"]), style="grey50")
                if rep.get("days_left") is not None:
                    txt.append(" ~%.0fd" % rep["days_left"], style="#FFFF00" if rep["days_left"] < 7 else "grey50")
                txt.append(" up %.0fh" % ((rep.get("uptime_s") or 0) / 3600), style="grey70")
                txt.append("\n      noise %s" % rep.get("noise_floor"), style="grey70")
            else:
                txt.append(" " + (rep.get("note") or "no poll yet"), style="#FF8000")
                txt.append("\n     ")
            tr = rep.get("trace_there")
            if tr is not None:
                txt.append(" trace %.1f/%.1f" % (tr, rep.get("trace_back") or 0), style="#00FFFF")
            if rep.get("ts"):
                txt.append(" " + time.strftime("%H:%M", time.localtime(rep["ts"])), style="grey42")
            txt.append("\n")
            best = rep.get("best")
            if best:
                h, n, secs, snr = best
                txt.append("      hears ", style="grey50")
                txt.append((n or h)[:12], style="bold #FFD700")
                txt.append(" %+.1fdB %s ago" % (snr or 0, self.ago(secs)), style="grey70")
                txt.append(" %d nbs" % len(rep.get("neighbors_all") or []), style="grey50")
            elif rep.get("neighbors_all"):
                txt.append("      hears only our own repeaters", style="grey50")
            else:
                txt.append("      no neighbour list yet", style="grey42")
            txt.append("\n")
        if not names:
            txt.append("none yet: click here, or type /repeaters,\nto pick yours or test the ones in range", style="grey42")
        self.query_one("#repeaters", Static).update(txt)

    def on_click(self, event: events.Click) -> None:
        """A click on the Repeaters panel opens the repeater dialog."""
        w = getattr(event, "widget", None)
        while w is not None:
            if getattr(w, "id", None) == "repeaters":
                self.open_repeaters()
                return
            w = w.parent

    def open_repeaters(self) -> None:
        if not self.engine:
            return

        def closed(_):
            self.show_repeaters(list(self.engine.repeater_rows.values()))
            self.focus_line()

        self.push_screen(RepeaterScreen(self.engine), callback=closed)

    def repeaters_report(self):
        """The /repeaters command: the full picture of each of our repeaters in the feed."""
        names = [r["name"] for r in self.engine.cfg.get("repeaters", [])]
        if not names:
            self.write_system("*** No repeaters in config.json.")
            return
        for name in names:
            rep = self.engine.repeater_report(name)
            line = Text(time.strftime("[%H:%M] "), style="#A0A0A0")
            line.append("*** %s: " % name, style="bold #00FF00")
            if not rep.get("ok"):
                line.append("last poll failed (%s)" % (rep.get("note") or "no answer"), style="#FF8000")
                self.query_one("#conversation", RichLog).write(line)
                continue
            pct = rep.get("percent")
            line.append("battery %.2f V" % ((rep.get("bat_mv") or 0) / 1000), style=self.battery_style(pct))
            if pct is not None:
                line.append(" (about %d%%)" % pct, style=self.battery_style(pct))
            if rep.get("mv_per_day") is None:
                line.append(", trend after a day of polls", style="#00FF00")
            elif rep["mv_per_day"] <= 5:
                line.append(", holding (%+d mV over the last day)" % -round(rep["mv_per_day"]), style="#00FF00")
            else:
                line.append(", losing %d mV a day" % round(rep["mv_per_day"]), style="#00FF00")
                if rep.get("days_left") is not None:
                    line.append(", roughly %.0f days to 3.4 V" % rep["days_left"],
                                style="#FFFF00" if rep["days_left"] < 7 else "#00FF00")
            line.append(". Up %.1f h, noise %s dBm, last RSSI %s, %s packets in / %s out, %s rx errors"
                        % ((rep.get("uptime_s") or 0) / 3600, rep.get("noise_floor"), rep.get("last_rssi"),
                           rep.get("nb_recv"), rep.get("nb_sent"), rep.get("recv_errors")), style="#00FF00")
            tr = rep.get("trace_there")
            if tr is not None:
                line.append(". Trace %.1f dB there, %.1f dB back" % (tr, rep.get("trace_back") or 0), style="#00FFFF")
            line.append(". Polled %s." % time.strftime("%H:%M", time.localtime(rep.get("ts", 0))), style="#00FF00")
            self.query_one("#conversation", RichLog).write(line)
            others = rep.get("others") or []
            line = Text(" " * 8)
            if others:
                line.append("hears best: ", style="grey70")
                for i, (h, n, secs, snr) in enumerate(others[:5]):
                    line.append(("" if i == 0 else ", ") + (n or h), style="bold #FFD700" if i == 0 else "#FFD700")
                    line.append(" %+.1f dB %s ago" % (snr or 0, self.ago(secs)), style="grey70")
                own = len(rep.get("neighbors_all") or []) - len(others)
                if own:
                    line.append(" (plus %d of ours)" % own, style="grey50")
            else:
                line.append("no neighbours reported yet", style="grey50")
            self.query_one("#conversation", RichLog).write(line)

    # ---- PIN handling ----
    def poll_pin(self):
        if self.engine and self.engine.pin_needed.is_set() and not self.asking_pin:
            self.asking_pin = True
            self.run_worker(self.ask_pin(), exclusive=False, name="pin")

    async def ask_pin(self):
        try:
            pin = await self.push_screen_wait(PinScreen(self.engine.node_name, "Pairing needed."))
        finally:
            self.asking_pin = False
        if pin:
            self.engine.set_pin(pin)
            self.save_pin(pin)

    def save_pin(self, pin: str):
        """Store only the PIN in the config file, leaving the rest as the user wrote it."""
        try:
            with open(self.cfg_path, encoding="utf-8-sig") as f:
                on_disk = json.load(f)
            if "connection" in on_disk:
                on_disk["connection"]["pin"] = pin
            else:
                on_disk["pin"] = pin
            with open(self.cfg_path, "w", encoding="utf-8") as f:
                json.dump(on_disk, f, indent=2)
        except (OSError, ValueError):
            pass

    # ---- modes, sending, rooms ----
    def apply_mode(self):
        op = self.engine.mode == "operator"
        self.screen_stack[0].set_class(op, "operator")  # the main screen, whatever is on top of it
        node = self.engine.node_name if self.engine.node_name != "?" else ""
        self.sub_title = "%s  %s" % (node, "OPERATOR" if op else "BOT")

    def action_mode(self):
        if not self.engine:
            return
        self.engine.set_mode("operator" if self.engine.mode == "bot" else "bot")
        self.apply_mode()
        self.write_system("*** %s" % ("Operator mode: the bot is silent, you talk (Enter to send)"
                                      if self.engine.mode == "operator" else "Bot mode: answering tests and beaconing"))

    def send_targets(self) -> list:
        t = [(name, ("chan", idx)) for idx, name in sorted(self.engine.channels.items())]
        for name, key in self.engine.find_contacts("", 40):
            t.append(("DM " + name, ("dm", key, name)))
        return t

    def current_target(self):
        """What the send window should point at: the window being looked at."""
        vk = self.view
        if vk == ALL:
            return ("chan", int(self.engine.beacon_cfg.get("channel", 1)))
        if vk[0] == "chan":
            return ("chan", vk[1])
        return ("dm", vk[1], self.view_names.get(vk, "?"))

    def channels_changed(self, channels: dict):
        self.rebuild_views()
        self.update_sendbar()
        if self.view == ALL:
            self.query_one("#conversation", RichLog).border_title = ", ".join(channels.values())
        try:  # remember rooms in config.json so they are listened to next time
            with open(self.cfg_path, encoding="utf-8-sig") as f:
                on_disk = json.load(f)
            on_disk["channels"] = {str(k): v for k, v in channels.items()}
            on_disk["rooms"] = self.engine.rooms
            with open(self.cfg_path, "w", encoding="utf-8") as f:
                json.dump(on_disk, f, indent=2)
        except (OSError, ValueError):
            pass

    async def action_send(self):
        if not self.engine or isinstance(self.screen, ModalScreen):
            return
        self.query_one("#send_line", Input).focus()

    async def send_dialog(self, preset: str = "", preset_target=None):
        targets = self.send_targets()
        if preset_target is not None and preset_target not in [t[1] for t in targets]:
            if preset_target[0] == "dm":
                targets.append(("DM " + preset_target[2], preset_target))
            else:
                preset_target = None
        res = await self.push_screen_wait(SendScreen(targets, self.engine.msgs.get("quick", []),
                                                     self.engine.msgs.get("emoticons", []), preset, preset_target))
        self.focus_line()
        if not res:
            return
        await self.send_to_target(res["target"], res["text"])

    async def action_room(self):
        if not self.engine or isinstance(self.screen, ModalScreen):
            return
        self.run_worker(self.room_dialog(), exclusive=False, name="room")

    async def room_dialog(self):
        inv = self.engine.pending_invite
        res = await self.push_screen_wait(RoomScreen(self.engine, inv))
        self.focus_line()
        if not res:
            return
        creator = inv["from"] if inv and res["name"] == inv["name"] else None
        idx, msg = await self.engine.add_room(res["name"], res["secret"], creator)
        self.write_system("*** Room: " + msg)
        if idx is None:
            return
        if inv and res["name"] == inv["name"]:
            self.engine.pending_invite = None
        self.select_view(("chan", idx))
        invite = self.engine.invite_text(self.engine.channels[idx], res["secret"])
        for name, key in res["invite"]:
            ok = await self.engine.send_dm(key, name, invite)
            self.write_system("*** Invite %s %s" % ("sent to" if ok else "NOT sent to", name))

    # ---- key actions ----
    def action_dashboard(self):
        if self.db is not None and not isinstance(self.screen, DashboardScreen):
            self.push_screen(DashboardScreen(), callback=lambda _: self.focus_line())

    async def action_beacon(self):
        if self.engine and self.engine.mc:
            await self.engine.send_beacon()

    async def action_test(self):
        """Send "Test" to the window being looked at (beacon channel in the All view)."""
        if not self.engine or not self.engine.mc or isinstance(self.screen, ModalScreen):
            return
        target = self.current_target()
        if target[0] == "chan":
            await self.engine.send_channel(target[1], "Test", kind="tx")
        else:
            await self.engine.send_dm(target[1], target[2], "Test")

    async def action_poll(self):
        if self.engine and self.engine.mc:
            self.show_event("Polling repeaters now...", "info")
            self.run_worker(self.engine.poll_repeaters(), exclusive=False, name="poll")

    def action_pause(self):
        if not self.engine:
            return
        self.engine.bot_paused = not self.engine.bot_paused
        self.write_system("*** Bot %s" % ("paused" if self.engine.bot_paused else "resumed"))

    async def action_quit(self):
        if self.engine:
            self.engine.stop()
            await asyncio.sleep(0.5)
        self.exit()  # on_unmount closes the database once the engine is down



def resolve_db(cfg: dict, cfg_path: str) -> str:
    db = cfg.get("db", "meshomit.sqlite")
    if not os.path.isabs(db):
        db = os.path.join(os.path.dirname(os.path.abspath(cfg_path)), db)
    return db


def default_config(cfg_path: str) -> dict:
    """The example config next to the program, used as the template on the first run."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    bundled = getattr(sys, "_MEIPASS", here)  # inside MeshOmit.exe the examples are unpacked here
    for cand in (os.path.join(os.path.dirname(os.path.abspath(cfg_path)), "config.example.json"),
                 os.path.join(here, "config.example.json"), os.path.join(bundled, "config.example.json")):
        if os.path.exists(cand):
            with open(cand, encoding="utf-8-sig") as f:
                return json.load(f)
    return {"db": "meshomit.sqlite", "channels": {"0": "Public", "1": "#test"},
            "bot": {"enabled": True, "reply_channels": [1], "triggers": ["test", "ping", "radio check"],
                    "per_sender_minutes": 10, "max_per_hour": 6, "delay_s": [2, 6],
                    "ignore_senders_containing": ["bot"], "brb_chance": 0.15, "answer_mentions": False},
            "beacon": {"enabled": True, "channel": 1, "interval_minutes": 10, "first_after_s": 60,
                       "reply_window_minutes": 10},
            "repeaters": [], "repeater_poll_minutes": 30, "repeater_first_after_s": 20, "known_prefixes": {},
            "human": {"slang_chance": 0.7, "typo_chance": 0.35}}


def load_config(path: str) -> dict | None:
    """The config, or None when there is none yet (the screen then runs the setup). Older files with a
    "device"/"pin" layout are read as a Bluetooth connection."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8-sig") as f:
        cfg = json.load(f)
    if "connection" not in cfg and "device" in cfg:
        cfg["connection"] = {"type": "ble", "address": cfg["device"].get("address"), "pin": cfg.get("pin")}
        cfg.setdefault("node_name", cfg["device"].get("name", ""))
    cfg["db"] = resolve_db(cfg, path)
    return cfg
