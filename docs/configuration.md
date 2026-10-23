# Configuration

Two files, both next to the program (next to `MeshOmit.exe` for the single-file build):

- `config.json`: how to reach the node, where you are, the channels, the bot's rules, the beacon, the
  repeaters. Written by the setup form on the first run; `config.example.json` lists every key with its
  default. Keep it private: it holds the node's Bluetooth address and PIN.
- `messages.json`: everything the bot says, the ready-made lines and the emoticons of the send window.

Both are read as UTF-8 (a byte-order mark, as some Windows editors write, is accepted). Edit, keep the
JSON valid, restart. Keys starting with `_` (`_help`) are comments and ignored.

## config.json

### connection

```json
"connection": {"type": "ble", "address": "AA:BB:CC:DD:EE:FF", "pin": null}
"connection": {"type": "serial", "port": "COM6", "baud": 115200}
"connection": {"type": "tcp", "host": "192.168.1.50", "port": 5000}
```

| key | meaning |
|---|---|
| `type` | `ble`, `serial` or `tcp` |
| `address` | Bluetooth address of the node (`ble`) |
| `pin` | the six-digit pairing PIN; `null` until the program asks for it and saves it |
| `port`, `baud` | serial port and speed (`serial`); the port is `COM6` on Windows, `/dev/ttyUSB0` or `/dev/ttyACM0` on Linux |
| `host`, `port` | address and port of the node's TCP companion interface (`tcp`, default port 5000) |

Only one Bluetooth client can use a node at a time; the phone app must be disconnected. On Windows the
pairing is done by the program through the Windows runtime with the PIN; on Linux and macOS the operating
system pairs (pair the node once in the Bluetooth settings or answer the PIN dialog).

### general

| key | default | meaning |
|---|---|---|
| `node_name` | `""` | your node's name; empty takes it from the node after connecting. Used in the texts (`{me}`), to recognise mentions, and to mark your own messages |
| `db` | `"meshomit.sqlite"` | the SQLite file, relative to `config.json` |
| `messages_file` | `"messages.json"` | the texts file, relative to `config.json` |
| `locations` | `["Springfield", "Downtown", "Riverside"]` | place names for `{location}`; one at random each time |
| `operator_location` | `""` | the place named in the operator's `/reply` lines, for example `"Springfield, IL"`; empty takes the first of `locations` |
| `channels` | `{"0": "Public", "1": "#test"}` | the channel slots the node listens to and their names. Index as on the node (0 to 7). The names are refreshed from the node at start |
| `contacts` | `{"manual": false}` | `true` puts the node in manual contact mode: it no longer adds every station it hears; adverts wait in `/add` and only the ones you add are kept, with a copy in `contacts.json` next to the config. `/contacts manual on` sets it too |
| `start_mode` | `"operator"` | `"bot"` starts answering and beaconing at once; otherwise the program starts as a chat client |
| `rooms` | `{}` | written by the room window: `{"#mytown": {"creator": "MyNode", "secret": null, "ts": 1760000000}}`; `secret` is the key in hex for private rooms |
| `known_prefixes` | `{}` | names for repeater hashes seen in packet paths, both the 2-byte and 1-byte form: `{"381f": "Hilltop", "38": "Hilltop"}`. Configured repeaters are added by themselves |

### bot

```json
"bot": {
  "enabled": true,
  "reply_channels": [1],
  "triggers": ["test", "ping", "radio check", "radio check?"],
  "per_sender_minutes": 10,
  "max_per_hour": 6,
  "delay_s": [2, 6],
  "ignore_senders_containing": ["bot"],
  "brb_chance": 0.15,
  "answer_mentions": false
}
```

| key | meaning |
|---|---|
| `reply_channels` | channel indexes the bot answers on. It listens on all of `channels`, but answers only here (1 = #test by default, so Public stays clean) |
| `triggers` | the whole message, lower-cased and with punctuation ignored, must be one of these |
| `per_sender_minutes` | one answer per station per this many minutes |
| `max_per_hour` | never more answers than this in a rolling hour |
| `delay_s` | wait a random time in this range before answering, so two bots do not collide |
| `ignore_senders_containing` | never answer a station whose name contains one of these (case-insensitive) |
| `brb_chance` | with this probability the answer is a line from the `brb` list instead of a real reply |
| `answer_mentions` | also answer people who write `@[YourNode] ...` without a test word, with a line from `mentions` |

`enabled: false` switches the answers off for good, in any mode; otherwise the mode (Operator or Bot)
decides whether the bot speaks.

### beacon

```json
"beacon": {"enabled": true, "channel": 1, "interval_minutes": 10, "first_after_s": 60, "reply_window_minutes": 10}
```

| key | meaning |
|---|---|
| `enabled` | `false` never sends beacons, in any mode |
| `channel` | channel index for the beacons; also where `t` and the *All* window send to |
| `interval_minutes` | time between beacons (in Bot mode; in Operator mode the timer runs but nothing is sent) |
| `first_after_s` | delay before the first beacon after connecting |
| `reply_window_minutes` | a message naming your node within this time after a beacon counts as a reply to it |

### repeaters

```json
"repeaters": [
  {"name": "Hilltop", "pubkey": "64 hex chars", "password_file": "C:/keys/hilltop.txt", "password_key": null}
],
"repeater_poll_minutes": 30,
"repeater_first_after_s": 20
```

| key | meaning |
|---|---|
| `name` | how the repeater is called on screen and in the database |
| `pubkey` | its public key, 64 hex characters, as the MeshCore app shows it |
| `password_file` | a text file with the admin password. With `password_key` set, the line `key=value` of that file is used (`admin_password=secret`); without it, the whole file is the password. Keep these files out of any repository |
| `repeater_poll_minutes` | time between polls |
| `repeater_first_after_s` | delay before the first poll after connecting |

An empty list switches repeater polling off.

### human

```json
"human": {"slang_chance": 0.7, "typo_chance": 0.35}
```

The human pass applied to every line the bot sends (answers and beacons, not your own typing):

- with `slang_chance`, per word, `you` becomes `u`, `your` → `ur`, `are` → `r`, `thanks` → `thx`,
  `please` → `pls`, `to` → `2`, `for` → `4`, `people` → `ppl`, `about` → `abt`, `okay` → `ok`,
  `because` → `cuz`, `tonight` → `2nite`, `good night` → `gud nite`. Whole words only; "to" inside
  "tomorrow" is left alone;
- with `typo_chance`, one word of at least four letters gets a slip: a doubled letter ("hearring"), a
  neighbouring key ("hesring") or two swapped letters ("haering"). Numbers, the `@[name]` mention and the
  words hops, direct, repeater, snr, rssi are never touched;
- the final full stop is dropped, and half the time a leading capital is lowered.

Set both chances to `0` for clean text.

### A complete example

```json
{
  "connection": {"type": "ble", "address": "AA:BB:CC:DD:EE:FF", "pin": "123456"},
  "node_name": "",
  "db": "meshomit.sqlite",
  "messages_file": "messages.json",
  "locations": ["Springfield", "Downtown", "Riverside"],
  "channels": {"0": "Public", "1": "#test"},
  "bot": {"reply_channels": [1], "triggers": ["test", "ping", "radio check"], "per_sender_minutes": 10,
          "max_per_hour": 6, "delay_s": [2, 6], "ignore_senders_containing": ["bot"], "brb_chance": 0.15,
          "answer_mentions": false},
  "beacon": {"enabled": true, "channel": 1, "interval_minutes": 10, "first_after_s": 60, "reply_window_minutes": 10},
  "repeaters": [],
  "repeater_poll_minutes": 30,
  "known_prefixes": {},
  "human": {"slang_chance": 0.7, "typo_chance": 0.35}
}
```

## messages.json

```json
{
  "replies":   ["@[{name}] hi, im in {location}, you?", "..."],
  "brb":       ["brb", "back in a bit", "..."],
  "beacons":   ["{greeting} from {location}, anyone around?", "..."],
  "mentions":  ["@[{name}] hi, yes im here in {location}", "..."],
  "quick":     ["Test", "hi all, anyone around?", "copy, thanks", "73"],
  "emoticons": [":)", ";)", ":D", ":P", ":(", "<3", "o/", "^^", "73", "+1"]
}
```

| list | used for |
|---|---|
| `replies` | answers to a test call. Each station gets every line once before any line repeats (the history is in the database) |
| `brb` | with `brb_chance` the answer is one of these, after the `@[name]` mention |
| `mentions` | answers to people who name your node without a test word (`answer_mentions`) |
| `beacons` | the periodic beacon; random, never the same line twice in a row |
| `operator_replies` | what `/reply` (key `a`) puts in the input line for you to send by hand; `{via}` is "via Hilltop>Ridge" or "direct". These lines skip the human pass |
| `quick` | the ready-made lines in the big send window |
| `snippets` | an object, not a list: your saved lines by key, `{"tx": "thank you"}`. `{{tx}}` in a message, or the window that opens on `{{`, which also edits them |
| `emoticons` | the buttons in the big send window |

Placeholders, filled in before the human pass:

| placeholder | value |
|---|---|
| `{name}` | the station being answered; keep `@[{name}]` at the start so the MeshCore apps highlight it |
| `{me}` | your node's name |
| `{location}` | one of `locations`, at random |
| `{hops}` | "direct, no repeater", "1 hop", "3 hops", or "a few hops" when unknown |
| `{snr}`, `{rssi}` | of the strongest copy heard; lines with `{snr}` are skipped when the SNR is unknown |
| `{greeting}` | hello, hi, hey, hi there, howdy. Never a time of day: the other side may be in another time zone |
| `{path}` | the repeater names of the path, comma separated, or `?` |
| `{daypart}` | morning, afternoon, evening, night, by your clock (not used by the default lines) |

Answers are cut at 160 characters after the human pass. If `messages.json` is missing, the program falls
back to lists named the same way in `config.json`, then to the lines built in.
