"""A stand-in for the meshcore-py MeshCore object: a contact list, a node identity and recorders for
everything the program would have sent. Enough for the screen and the engine's bookkeeping; no radio."""
import asyncio
import json
import os
import shutil
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ALICE_KEY = "abcdef0123456789" * 4
BOB_KEY = "1234560123456789" * 4


class _Result:
    def __init__(self, ok=True, payload=None):
        self.type = type("T", (), {"name": "OK" if ok else "ERROR"})()
        self.payload = payload or {}


class FakeMC:
    def __init__(self):
        now = int(time.time())
        self.contacts = {
            ALICE_KEY: {"adv_name": "Alice T-Deck", "last_advert": now - 900, "type": 1, "out_path_len": 2,
                        "adv_lat": 33.9526, "adv_lon": -84.5499},
            BOB_KEY: {"adv_name": "Bob Heltec", "last_advert": now - 7200, "type": 2, "out_path_len": 0,
                      "adv_lat": 0.0, "adv_lon": 0.0},
        }
        self.self_info = {"name": "TestNode", "adv_lat": 33.9800, "adv_lon": -84.4700}
        self.is_connected = True
        self.sent: list = []            # ("chan", idx, text) | ("dm", key, text) | ("set_channel", idx, name, secret)
        self.node_channels = {0: "Public", 1: "#test"}
        self.pending_contacts: dict = {}
        self.manual = False
        fake = self

        class Cmds:
            async def send_chan_msg(self, idx, text):
                fake.sent.append(("chan", idx, text))
                return _Result()

            async def send_msg(self, key, text):
                fake.sent.append(("dm", key, text))
                return _Result()

            async def get_channel(self, idx):
                return _Result(payload={"channel_name": fake.node_channels.get(idx, "")})

            async def set_channel(self, idx, name, secret):
                fake.sent.append(("set_channel", idx, name, secret))
                fake.node_channels[idx] = name
                return _Result()

            async def get_msg(self, timeout=None):
                return type("R", (), {"type": type("T", (), {"name": "NO_MORE_MSGS"})()})()

            async def send_appstart(self, timeout=None):
                return _Result()

            async def get_contacts(self, timeout=None):
                return _Result()

            async def add_contact(self, contact):
                fake.sent.append(("add_contact", contact.get("public_key")))
                return _Result()

            async def remove_contact(self, key):
                fake.sent.append(("remove_contact", key))
                return _Result()

            async def set_manual_add_contacts(self, on):
                fake.manual = on
                r = _Result()
                r.is_error = lambda: False
                return r

        self.commands = Cmds()

    def pop_pending_contact(self, key):
        return self.pending_contacts.pop(key, None)

    async def stop_auto_message_fetching(self):
        pass

    async def disconnect(self):
        self.is_connected = False


def event(payload: dict):
    """What meshcore-py hands to a subscriber."""
    return type("E", (), {"payload": payload})()


def channel_msg(idx: int, sender: str, text: str, hops: int = 1, snr: float = 5.0, ts=None):
    return event({"channel_idx": idx, "text": "%s: %s" % (sender, text), "sender_timestamp": ts or time.time(),
                  "path_len": hops, "SNR": snr})


def dm(prefix: str, text: str, snr: float = 7.0):
    return event({"pubkey_prefix": prefix, "text": text, "SNR": snr, "path_len": 1, "sender_timestamp": time.time()})


def make_config(tmp_dir: str, channels=None, beacon_channel=1) -> str:
    """A config.json in tmp_dir built from config.example.json: TCP to nowhere, no beacons, no repeaters."""
    with open(os.path.join(ROOT, "config.example.json"), encoding="utf-8-sig") as f:
        cfg = json.load(f)
    cfg["connection"] = {"type": "tcp", "host": "127.0.0.1", "port": 1}
    cfg["db"] = os.path.join(tmp_dir, "test.sqlite")
    shutil.copy(os.path.join(ROOT, "messages.json"), os.path.join(tmp_dir, "messages.json"))
    cfg["messages_file"] = "messages.json"
    cfg["beacon"]["enabled"] = False
    cfg["beacon"]["channel"] = beacon_channel
    cfg["repeaters"] = []
    cfg["rooms"] = {}
    cfg["node_name"] = "TestNode"
    cfg["channels"] = channels or {"0": "Public", "1": "#test"}
    path = os.path.join(tmp_dir, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    return path


async def start(app, pilot):
    """Give the app its fake node once the screen is up."""
    await pilot.pause(0.5)
    eng = app.engine
    eng.mc = FakeMC()
    eng.contacts_loaded = True
    await asyncio.sleep(0)
    return eng
