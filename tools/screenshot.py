"""Render the screenshots in docs/ from a headless run with the fake node and made-up traffic.
Run from the repository root: python tools/screenshot.py"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time

os.environ.pop("NO_COLOR", None)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

from textual.widgets import Input, RichLog  # noqa: E402

from fake_node import ALICE_KEY, channel_msg, dm, event, make_config, start  # noqa: E402
from meshomit.app import MeshOmitApp, load_config  # noqa: E402

OUT = os.path.join(ROOT, "docs")
SIZE = (150, 50)


def rx_copy(sender_ts, sender, text, chan, path, snr, rssi):
    """One copy of a channel message as the radio log reports it (path = hashes of the repeaters)."""
    return event({"path": path, "path_hash_size": 2, "payload_typename": "GRP_TXT", "route_typename": "FLOOD",
                  "snr": snr, "rssi": rssi, "chan_name": chan, "sender_timestamp": sender_ts,
                  "message": "%s: %s" % (sender, text)})


async def main():
    tmp = tempfile.mkdtemp(prefix="meshomit_shot_")
    cfg_path = make_config(tmp, {"0": "Public", "1": "#test"})
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    cfg["node_name"] = "MyNode"
    cfg["locations"] = ["Springfield", "Downtown", "Riverside"]
    cfg["known_prefixes"] = {"1a2b": "Hilltop", "1a": "Hilltop", "3c4d": "Ridge", "3c": "Ridge"}
    cfg["connection"] = {"type": "tcp", "host": "10.255.255.1", "port": 1}  # never answers: no "link lost" lines
    json.dump(cfg, open(cfg_path, "w", encoding="utf-8"), indent=1)
    app = MeshOmitApp(load_config(cfg_path), cfg_path)
    async with app.run_test(size=SIZE) as pilot:
        eng = await start(app, pilot)
        eng.node_name = "MyNode"
        now = int(time.time())
        eng.mc.self_info = {"name": "MyNode", "adv_lat": 39.80, "adv_lon": -89.65}
        for c in eng.mc.contacts.values():  # the fake node's two contacts live nearby too
            c["adv_lat"], c["adv_lon"] = (39.76, -89.61) if c["adv_name"].startswith("Alice") else (39.84, -89.69)
        app.query_one("#events", RichLog).clear()
        people = {"K1ABC": (39.78, -89.70, 2), "N2XYZ Mobile": (39.83, -89.60, 1), "W3DEF": (0, 0, 3),
                  "KD4GHI": (39.72, -89.66, 2), "Hilltop": (39.85, -89.72, 0)}
        for i, (name, (lat, lon, hops)) in enumerate(people.items()):
            eng.mc.contacts["%064x" % (0x1000 + i)] = {"adv_name": name, "last_advert": now - 600 * (i + 1),
                                                       "type": 2 if name == "Hilltop" else 1, "out_path_len": hops,
                                                       "adv_lat": lat, "adv_lon": lon}
        eng.log("Connected: MyNode", "ok")
        eng.log("Listening on Public, #test", "ok")
        eng.log("Contacts: 212 known to the node", "ok")
        eng.log("Pulled 2 queued messages the node had not pushed")
        eng.log("Hilltop: 4.09 V, up 44.4 h, noise -117, trace 13.2/9.2", "ok")

        def heard(idx, chan, sender, text, hops, paths, snrs, ts_off):
            ts = now - ts_off
            for path, snr in zip(paths, snrs):
                eng.on_rx_log(rx_copy(ts, sender, text, chan, path, snr, -90 - int(snr)))
            eng.on_channel_msg(channel_msg(idx, sender, text, hops=hops, snr=max(snrs), ts=ts))

        heard(0, "Public", "K1ABC", "good morning mesh, anyone around?", 2, ["1a2b3c4d", "1a2b"], [6.5, 4.0], 1500)
        heard(0, "Public", "W3DEF", "morning! hearing you fine from the lake", 3, ["3c4d1a2b"], [-2.5], 1380)
        heard(1, "#test", "N2XYZ Mobile", "Test", 1, ["1a2b"], [8.2], 1200)
        app.show_message({"ts": now - 1196, "channel_idx": 1, "channel_name": "#test", "sender": "MyNode",
                          "text": "@[N2XYZ Mobile] hearing u ok, 1 hop. how about u?", "kind": "bot_reply",
                          "hops": None, "snr": None, "path_names": [], "is_trigger": 0})
        heard(1, "#test", "N2XYZ Mobile", "@[MyNode] loud and clear, 1 hop via Hilltop", 1, ["1a2b"], [7.8], 1100)
        app.show_message({"ts": now - 900, "channel_idx": 1, "channel_name": "#test", "sender": "MyNode",
                          "text": "hi all, MyNode in Springfield, who hears me?", "kind": "beacon",
                          "hops": None, "snr": None, "path_names": [], "is_trigger": 0})
        heard(1, "#test", "KD4GHI", "MyNode got you 2 hops here, nice signal", 2, ["3c4d1a2b"], [3.1], 820)
        heard(0, "Public", "K1ABC", "anyone going to the club meeting tonight?", 2, ["1a2b3c4d"], [5.9], 400)
        eng.on_contact_msg(dm("abcdef012345", "hey, you around tonight? bring the antenna analyzer :)"))
        await pilot.pause(0.2)
        await eng.send_dm(ALICE_KEY, "Alice T-Deck", "yes, till 10. will do o/")
        await eng.add_room("#mytown", None)
        await pilot.pause(0.3)
        app.select_view(("all",))
        eng.db.add_beacon(1, "hi all, MyNode in Springfield, who hears me?", 2)
        eng.db.add_beacon(1, "quiet here in Downtown.. anyone?", 0)
        row = {"name": "Hilltop", "pubkey": "1a2b" + "0" * 60, "ok": 1, "bat_mv": 4090, "uptime_s": 159840,
               "noise_floor": -117, "last_rssi": -92, "nb_recv": 1820, "nb_sent": 1534, "recv_errors": 3,
               "airtime": 4200, "tx_queue": 0, "sent_flood": 900, "sent_direct": 634, "recv_flood": 1500,
               "recv_direct": 320, "trace_there": 13.2, "trace_back": 9.2, "note": ""}
        eng.db.add_repeater_status(**row)
        row["ts"] = now - 300
        row["neighbors"] = [("3c4d00", "Ridge", 120, 9.5), ("9a8b00", "Lakeview", 40, 6.2), ("77ee00", "Tower2", 900, -1.5)]
        ridge = {"name": "Ridge", "pubkey": "3c4d" + "0" * 60, "ok": 1, "bat_mv": 3980, "uptime_s": 72000,
                 "noise_floor": -114, "trace_there": 7.5, "trace_back": 5.0, "ts": now - 290,
                 "neighbors": [("1a2b00", "Hilltop", 130, 10.1), ("9a8b00", "Lakeview", 300, 2.8)]}
        eng.cfg["repeaters"] = [{"name": "Hilltop", "pubkey": "1a2b" + "0" * 60}, {"name": "Ridge", "pubkey": "3c4d" + "0" * 60}]
        eng.repeater_rows = {"Hilltop": row, "Ridge": ridge}
        app.show_repeaters([row, ridge])
        app.show_status({"state": "listening", "node": "MyNode", "address": "Bluetooth AA:BB:CC:DD:EE:FF",
                         "since": now - 5400, "started": now - 5500, "next_beacon": now + 290, "next_poll": now + 1500,
                         "bot_paused": False, "mode": "operator", "contacts": 212,
                         "counters": {"messages": 41, "triggers": 6, "replies": 5, "beacons": 3, "beacon_replies": 2},
                         "relays_1h": {"1a2b": 14, "3c4d": 9, "": 5}})
        app.refresh_nicks()
        inp = app.query_one("#send_line", Input)
        inp.value = "hello everyone, anyone around tonight?"
        inp.cursor_position = len(inp.value)
        await pilot.pause(0.4)
        app.save_screenshot(os.path.join(OUT, "screenshot-main.svg"))

        # the big send window
        inp.value = ""
        await pilot.press("enter")
        await pilot.pause(0.5)
        app.screen.query_one("#send_text", Input).value = "good copy here, how do you hear me? :)"
        await pilot.pause(0.3)
        app.save_screenshot(os.path.join(OUT, "screenshot-send.svg"))
        await pilot.press("escape")
        await pilot.pause(0.3)

        # bot mode: the blue theme
        app.action_mode()
        app.show_status({"state": "listening", "node": "MyNode", "address": "Bluetooth AA:BB:CC:DD:EE:FF",
                         "since": now - 5400, "started": now - 5500, "next_beacon": now + 290, "next_poll": now + 1500,
                         "bot_paused": False, "mode": "bot", "contacts": 212,
                         "counters": {"messages": 41, "triggers": 6, "replies": 5, "beacons": 3, "beacon_replies": 2},
                         "relays_1h": {"1a2b": 14, "3c4d": 9, "": 5}})
        await pilot.pause(0.4)
        app.save_screenshot(os.path.join(OUT, "screenshot-bot.svg"))

        # the dashboard
        app.action_dashboard()
        await pilot.pause(0.8)
        app.save_screenshot(os.path.join(OUT, "screenshot-dashboard.svg"))
        await pilot.press("escape")
        await pilot.pause(0.2)
        eng.stop()
        await pilot.pause(0.3)
    shutil.rmtree(tmp, ignore_errors=True)
    print("screenshots written to", OUT)


asyncio.run(main())
