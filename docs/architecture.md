# Architecture

MeshOmit is a Python 3.11+ program of about 2,700 lines in one package, `meshomit/`. It has two halves
that know little about each other: the **engine** (`core.py`), which talks to the node and holds every
rule, and the **screen** (`app.py`), a Textual application that draws what the engine reports and sends
the user's actions back. The link to the node is behind `connection.py`.

```
 ┌────────────┐  events / messages / status  ┌────────────┐  commands  ┌─────────────┐  BLE / serial / TCP  ┌──────┐
 │  app.py    │ <─────────────────────────── │  core.py   │ ─────────> │ meshcore-py │ <──────────────────> │ node │
 │  (Textual) │ ───────────────────────────> │  (Engine)  │ <───────── │  (MeshCore) │                      └──────┘
 └────────────┘  send, rooms, mode, pin      └─────┬──────┘  events    └─────────────┘
                                                   │
                                             ┌─────┴──────┐
                                             │   db.py    │  SQLite, WAL
                                             └────────────┘
```

## Modules

| module | lines | role |
|---|---|---|
| `__main__.py` | 25 | entry point. Clears a stray `NO_COLOR`, finds `config.json` next to the program (next to the exe when frozen), loads it, runs the app |
| `app.py` | 1300 | the Textual screen: CSS, `PinScreen`, `SetupScreen`, `SendScreen`, `RoomScreen`, `DashboardScreen`, `MeshOmitApp` |
| `core.py` | 850 | `Engine`: connection loop, event handlers, contacts, direct messages, rooms, the bot, beacons, repeater polling; `load_messages`, `read_password`, `distance_km` |
| `db.py` | 250 | `Db`: schema, inserts, the queries behind the dashboard |
| `connection.py` | 110 | `connect()` dispatching on the connection type, `is_alive()`, `scan_ble()`, `serial_ports()`, the phone hint |
| `ble.py` | 90 | Windows Bluetooth: radio check, pairing, connect with a subscribe retry, app start |
| `pairing.py` | 75 | the Windows runtime calls: is the device paired, pair with a PIN, unpair, switch the radio on |
| `meshomit_exe.py` | 5 | the PyInstaller entry point |

## The engine

`Engine(cfg, db, ui, cfg_path)` is created by the screen with a `ui` object that implements four
methods; the engine never imports Textual:

| ui method | called with |
|---|---|
| `event(text, level)` | a progress or problem line (`info`, `ok`, `warn`), also stored in `events` |
| `message(rec)` | a conversation line: a dict with `ts`, `channel_idx`, `channel_name`, `sender`, `text`, `kind`, `hops`, `snr`, `rssi`, `path_names`, and for direct messages `dm_key` and `to` |
| `status(dict)` | state, node name, link, timers, counters, contact count, mode |
| `repeaters(rows)` | the latest reading of every repeater |

The screen calls the engine directly: `send_channel`, `send_dm`, `add_room`, `invite_text`, `set_mode`,
`send_beacon`, `poll_repeaters`, `find_contacts`, `contact_info`, `set_pin`, `stop`.

### The connection loop

`Engine.run()` loops until stopped:

1. `connect_and_serve()`: `connection.connect()` returns a `MeshCore` object after the app-start handshake;
   `setup()` sets the node's clock when it is more than 30 s off (repeaters drop logins with a stale
   timestamp), reads the channel names, switches on decrypted channel logs, subscribes to `RX_LOG_DATA`,
   `CHANNEL_MSG_RECV` and `CONTACT_MSG_RECV`, and starts the library's automatic message fetching.
2. Five tasks run for the life of the link: `beacon_loop`, `repeater_loop`, `status_loop` (every 5 s),
   `load_contacts` (once, with retries), `pull_loop` (every 20 s).
3. The loop checks `connection.is_alive()` every 2 s and raises when the link dropped. The tasks are
   cancelled, the link closed, and after 10 s it connects again.
4. A `PairingError` (Bluetooth needs a new PIN) sets `pin_needed`; the screen shows the PIN dialog and
   calls `set_pin`, and the loop goes on.

Every command to the node runs under `cmd_lock`, because the companion protocol answers one request at a
time and the library matches answers to requests by type.

### Two quirks worth knowing

- **Contacts.** `get_contacts` right after connecting returns nothing on some boards (the firmware's
  contact iterator is only reset by an app start). `load_contacts` waits 3 s, sends an app start, asks
  for the list with a 20 s timeout, and retries twice 30 s apart. With a few hundred contacts the list
  streams in over about a minute.
- **Queued messages.** The library fetches messages when the node pushes "messages waiting". That push
  can be missed right after connecting, in which case nothing ever arrives although the node decrypts
  everything (visible in `rx_packets`). `pull_loop` asks for queued messages every 20 s regardless, until
  the node answers "no more", and logs how many it found.

### Receiving

`on_rx_log` records every packet the radio hears (type, route, SNR, RSSI, path hashes, the last hop, and
the decrypted text and channel for channel messages) in `rx_packets` and in a short memory.

`on_channel_msg` splits `Name: text`, finds the strongest copy of the same message in that memory (the
companion reports only one copy, the raw log reports every repeater's copy) to attach SNR, RSSI, hops and
path, marks messages older than 2 minutes as `backlog` (queued on the node before the program started),
decides whether the text is a trigger or a mention, counts beacon replies, stores the record, hands it to
the screen, and starts `maybe_reply` as a task when the bot should answer.

`on_contact_msg` handles direct messages: answers to a repeater CLI command the poller is waiting for are
routed to it by the sender's key prefix; everything else is a `dm` record with the sender resolved from
the contact list. An invitation ("join me on channel NAME[, key HEX]") is parsed into `pending_invite`.

### The bot

`maybe_reply(rec, which)` applies the rules in order: mode and pause, ignored senders, per-sender
interval, hourly limit, random delay. `build_reply` picks a template this sender has not had (history in
`reply_history`, cleared when exhausted), skips `{snr}` lines when the SNR is unknown, fills the
placeholders, and runs `humanize`. `send_channel` sends and records the answer with `reply_to` pointing at
the message answered.

`beacon_loop` waits `first_after_s`, then every `interval_minutes` sends a beacon in Bot mode (picked at
random, never the same twice in a row) and remembers it as `current_beacon`; messages naming the node
within the reply window are counted on it.

### Rooms

`add_room(name, secret, creator)` finds a free slot among the node's 8 channels (slots the node already
uses are adopted), programs the channel with `set_channel`, re-reads it so the library registers the key
for decoding, records the room with its creator and key, and notifies the screen through
`on_channels_changed`, which saves `channels` and `rooms` to `config.json`. A name without `#` and
without a secret is given a `#`. `invite_text` builds the invitation line that the screen sends by
direct message.

### Repeaters

`poll_one` for each configured repeater, taking the command lock only while a command goes out so typed
messages are not held up: a 2-byte-hash trace with the result's
SNR there and back; login with the password from the file; status request; the `neighbors` CLI command,
whose answer arrives as direct messages collected through `pending_cli` for 8 s and parsed line by line.
Results go to `repeater_status` and `repeater_neighbors` and to the screen.

## The screen

`MeshOmitApp` composes a header, the feed (`RichLog`), the input line (`Label` + `Input`), the right
column (status `Static`, two `OptionList`s for windows and nicks, a `DataTable` for repeaters, a
`RichLog` for events) and a footer with the key bindings.

- **Windows.** `views` is the ordered list of window keys: `("all",)`, `("chan", idx)` and `("dm", key)`.
  Every line shown is kept in `lines` with its window key (trimmed at 4,000), so switching windows
  re-renders the feed from memory. `unread` counts per window; `users` records per nick when it was last
  heard in each window for the nick list.
- **Names in the feed** are Rich `Text` spans with a `Style` carrying `@click=app.nick_click(name, chan)`
  metadata; Textual turns such spans into links that highlight under the mouse (the `link-*-hover` CSS on
  the feed) and runs the action on click.
- **The input line** handles `Input.Submitted`: empty opens the big send window, `/...` goes to
  `command()`, anything else to `send_to_target(current_target(), text)`. `current_target()` is the window
  being looked at (the beacon channel for *All*). Escape unfocuses the line so the single-key bindings
  apply; Enter focuses it again.
- **Dialogs** are `ModalScreen`s run with `push_screen_wait` inside a worker: `SendScreen` returns
  `{"target", "text"}`, `RoomScreen` returns `{"name", "secret", "invite"}`, `PinScreen` a string,
  `SetupScreen` the new config. Focus returns to the input line afterwards.
- **Modes** add or remove the `operator` class on the screen; the CSS switches the colours.
- **The dashboard** is a plain `Screen` with `Static` cards, `Sparkline`s and `DataTable`s filled from
  `db` queries every 30 s.

The engine's `ui` callbacks are called from the asyncio loop the app runs on, so they touch widgets
directly (no thread hopping).

## The connection layer

`connection.connect(conn_cfg, pin, log, timeout)` returns a connected `MeshCore` with the handshake done,
or raises `PairingError` (Bluetooth needs a PIN) or `ConnectionError`.

- `serial` and `tcp` use the library's `create_serial` and `create_tcp`.
- `ble` on Linux and macOS uses `create_ble` (the operating system pairs).
- `ble` on Windows goes through `ble.py`: `pairing.bluetooth_on()` switches the radio on if needed;
  `pairing.is_paired` / `pair_with_pin` do passkey pairing through `Windows.Devices.Enumeration` (bleak
  cannot supply a PIN); then a `BleakClient` connects, subscribes to the UART TX characteristic with up to
  three attempts (Windows sometimes cancels the first subscribe), and the app start is sent. A stale bond
  shows up as "Unreachable" and is removed so the next attempt pairs again. The MeshCore object is built
  around the library's `BLEConnection` with the client kept on `mc._link_client` for liveness checks.
- Every failure path logs the phone hint: a node accepts one Bluetooth link at a time.
- `scan_ble` lists devices with MeshCore nodes first; `serial_ports` lists the ports.

## Database

`meshomit.sqlite`, WAL mode, created by `Db.__init__` from `SCHEMA`.

| table | one row per | main columns |
|---|---|---|
| `messages` | channel message or direct message, in or out | `ts` (received or sent), `sender_ts`, `channel_idx`, `channel_name` (`DM` for direct), `sender`, `text`, `hops`, `snr`, `rssi`, `path`, `copies`, `kind`, `is_trigger`, `reply_to`, `beacon_id` |
| `beacons` | beacon sent | `ts`, `channel_idx`, `text`, `replies`, `message_id` |
| `rx_packets` | packet heard by the radio | `ts`, `payload_type`, `route_type`, `snr`, `rssi`, `hash_size`, `hops`, `path`, `last_hop`, `channel_name`, `sender_ts`, `text` |
| `repeater_status` | repeater poll | `ts`, `name`, `pubkey`, `ok`, `bat_mv`, `uptime_s`, `noise_floor`, `last_rssi`, packet counters, `airtime`, `tx_queue`, `trace_there`, `trace_back`, `note` |
| `repeater_neighbors` | neighbour reported at a poll | `ts`, `repeater`, `neighbor`, `neighbor_name`, `secs_ago`, `snr` |
| `reply_history` | reply line given to a station | `ts`, `sender`, `template` (index into `replies`; mentions use the key `mentions|name`) |
| `events` | event line | `ts`, `level`, `text` |

Values of `messages.kind`:

| kind | meaning |
|---|---|
| `rx` | a channel message received |
| `backlog` | received, but written more than 2 minutes before it arrived (queued on the node) |
| `beacon_reply` | received and counted as a reply to our beacon |
| `bot_reply` | the bot's answer to a test or mention |
| `beacon` | a beacon we sent |
| `tx` | a message you typed |
| `dm` | a direct message received |
| `dm_tx` | a direct message you sent |

The dashboard queries are in `db.py`: `stats`, `hourly`, `top_senders`, `relay_counts`, `hops_histogram`,
`beacon_summary`, `beacon_history`, `repeater_names`, `last_repeater_status`, `repeater_history`,
`recent_replies`.

## Packaging

`build_exe.cmd` runs PyInstaller in one-file mode, collecting Textual, Rich, meshcore, bleak, the `winrt`
and `serial` submodules, and bundling `messages.json` and `config.example.json`. When frozen,
`__main__.py` looks for `config.json` next to the executable and `load_messages` falls back to the
bundled `messages.json` in `sys._MEIPASS` when there is none next to it.
