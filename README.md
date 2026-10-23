# MeshOmit

An IRC-style terminal client and test-reply bot for a [MeshCore](https://github.com/ripplebiz/MeshCore)
companion node, in Python. Connect a Cardputer, T-Deck, Heltec, RAK or any other board running the
companion firmware over Bluetooth, USB serial or WiFi, and MeshOmit gives you:

- **a chat screen like a classic IRC client**: one window per channel, room and private conversation,
  a nick list, `<name>` lines in one colour per station, an input line with a target label, slash
  commands, unread counters, clickable names;
- **two modes**: *Operator* (you chat, the bot is silent) and *Bot* (it answers "test", "ping" and
  "radio check" the way a person would, sends a beacon every few minutes and counts the replies);
- **rooms and invites**: create a hashtag room or a private room with a random key and invite people by
  encrypted direct message; invitations you receive are joined with one key press;
- **repeater logging**: logs in to your repeaters, records battery, uptime, noise floor, counters, trace SNR
  and the neighbour list every half hour;
- **a dashboard** of the last 24 hours and all time: messages and tests per hour, answer rate, beacon hit
  rate, stations heard, which repeater carries the traffic, hops histogram;
- **everything stored in SQLite**, safe to query while the program runs;
- **a single-file Windows executable** for people who do not want to install Python.

Everything the bot says comes from `messages.json`; every rule is in `config.json`. Nothing is hard-coded.

## Quick start

Python 3.11 or newer.

```
pip install -r requirements.txt
meshomit.cmd          Windows
./meshomit.sh         Linux, macOS
```

The first start opens a setup form: pick Bluetooth (press *Scan for devices*), USB serial or TCP, give a
few place names, save. The program connects, asks for the Bluetooth PIN shown on the node's screen if the
node is not paired yet, and shows the channels. It starts in Operator mode; type `/bot` or press `m` to let
the bot answer tests and send beacons.

Windows users can instead download `MeshOmit.exe` from the releases page, put it in a folder next to
`messages.json` and double-click it.

## Documentation

| document | content |
|---|---|
| [docs/user-guide.md](docs/user-guide.md) | the screen, windows, input line, commands, keys, modes, rooms, private messages, whois, dashboard |
| [docs/configuration.md](docs/configuration.md) | every key of `config.json` and every list of `messages.json`, the human pass |
| [docs/architecture.md](docs/architecture.md) | how the program is built: modules, engine and screen, asyncio tasks, connection layer, database schema |
| [docs/building.md](docs/building.md) | running from source, building `MeshOmit.exe`, running the tests |
| [docs/troubleshooting.md](docs/troubleshooting.md) | grey colours, a phone holding the node, PIN, missing contacts, no messages |
| [CHANGELOG.md](CHANGELOG.md) | what changed |
| [CREDITS.md](CREDITS.md) | the projects and people MeshOmit builds on |

## A look at the screen

```
 MeshOmit                                                                       16:42:10
┌─ #test ─────────────────────────────────────────────┐┌─ Status ──────────────────────┐
│ [16:30] #test  <K1ABC> Test                        ││ OPERATOR  you chat, bot off   │
│ [16:30] #test  <MyNode> @[K1ABC] hi, im in East    ││ node   MyNode                 │
│         Cobb, you?                                  ││ link   Bluetooth              │
│ [16:33] #test  <N2XYZ Mobile> good copy, 2 hops     ││ contacts 350                  │
│                                                     │└───────────────────────────────┘
│                                                     │┌─ Windows (1-9) ───────────────┐
│                                                     ││ 1 All                         │
│                                                     ││ 2 Public  (3)                 │
│                                                     ││ 3 #test                       │
│                                                     ││ 4 #mytown  *MyNode          │
│                                                     ││ 5 -> K1ABC                   │
│                                                     │└───────────────────────────────┘
│                                                     │┌─ Nicks (last 3 h) ────────────┐
│                                                     ││ K1ABC          2h 8.0km W x3 │
│                                                     ││ N2XYZ Mobile    direct x1     │
└─────────────────────────────────────────────────────┘└───────────────────────────────┘
 #test  hello everyone, anyone around tonight?_
 q Quit  m Bot/Operator  j Room  d Dashboard  b Beacon now  t Send Test  r Poll  p Pause
```

The names and call signs above are made up.

## Files

```
meshomit/            the program: app.py (screen), core.py (engine), connection.py, ble.py, pairing.py, db.py
messages.json        what the bot says, the quick lines and the emoticons
config.example.json  every setting with its default; the setup form writes config.json for you
meshomit.cmd, meshomit.sh   launchers
build_exe.cmd, meshomit_exe.py   the Windows single-file build
tests/               headless tests of the screen with a fake node
docs/                the documentation
```

`config.json`, the SQLite database and the build output are ignored by git on purpose: they hold your
node's Bluetooth address, PIN and traffic.

## Licence

MIT, Copyright (c) 2026 opensourcera. See `LICENSE` and `CREDITS.md`.
