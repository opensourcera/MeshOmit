# Changelog

## 1.0.1 beta (2026-10-24)

- Setup form: the Bluetooth device list was clipped away by its container and never visible; the
  connection sections now size to their content. The scan starts by itself when the form opens and
  the list fills as devices answer, MeshCore nodes first in green; the button is "Scan again".
- Windows exe: the build left out a Windows Bluetooth module that the scanner loads lazily, so the
  exe's scan always reported 0 devices. The build script names the modules now.
- `MESHOMIT_DEBUG=1` writes `meshomit-debug.log` with the Bluetooth stack's own messages.
- The 1.0.0 Windows zip was built before the Repeaters panel, `/reply`, `{` fields, `{{` snippets,
  the `@` people list and manual contacts; this zip has all of them.

## 1.0.0 beta (2026-10-23)

First public release, as a beta.

- IRC-style screen built with Textual: feed, status, window list, nick list, repeater table, event log.
- Windows per channel, room and private conversation, with unread counters and a nick list per window.
- Input line under the feed with a target label, Enter sends to the window being looked at, slash
  commands (`/w`, `/query`, `/msg`, `/whois`, `/bot`, `/op`, `/join`, `/send`, `/dash`, `/beacon`,
  `/test`, `/poll`, `/pause`, `/quit`, `/help`).
- Big send window with a 140-character counter, emoticon buttons and ready-made lines.
- Names in the feed light up under the mouse; a click opens a private window or types a mention.
- Operator and Bot modes; the program starts in Operator mode.
- Bot: answers test calls with lines from `messages.json`, never the same line twice to the same station,
  per-station and hourly limits, random delay, "brb" now and then, optional answers to mentions, a human
  pass with short words and the odd typo.
- Beacons every N minutes with reply counting.
- Rooms: hashtag rooms and private rooms with a random key, invitations by direct message, one-key join
  of received invitations, the inviter marked as the room's creator.
- `/whois`: contact type, last advert, hops, position with a map link, distance and direction.
- `/reply` and the `a` key: a factual answer to the last test call (name, hops, repeaters, SNR, place)
  prepared in the input line for the operator to send by hand.
- Fields in typed messages: `{` opens a list of `{hops}`, `{via}`, `{snr}`, `{rssi}`, `{heard}`,
  `{location}`, `{time}`, `{name}`, `{me}`, filled in when the message is sent for the station addressed.
  The same list offers the emoticons, shown as pictures and inserted as text.
- `@` in a message opens the list of stations heard in the last 3 hours and inserts a mention.
- Contacts: manual mode (`contacts.manual`), `/add` of waiting adverts, `/forget`, `/contacts export`,
  `/contacts clear yes` with a backup, `/contacts restore` from `contacts.json`.
- Repeaters panel: battery percentage and daily drain, best neighbour that is not ours; `/repeaters`
  prints the full report with days left on battery and the top neighbours.
- Saved lines: `{{` opens a window of your own short texts (`{{tx}}` thank you, ...), with fields allowed
  inside, added, edited and deleted in place and kept in `messages.json`.
- Repeater polling: trace, login, status, neighbour list, all stored.
- Dashboard with cards, sparklines and tables for the last 24 hours and all time.
- Connections: Bluetooth LE (Windows pairing with a PIN through the Windows runtime, radio switched on
  when off), USB serial, TCP.
- A periodic pull of queued messages, because the node's "messages waiting" push can be missed right
  after connecting.
- First-run setup form; `config.json` written for you. The Bluetooth scan starts by itself and lists
  devices as they answer, MeshCore nodes first.
- Single-file `MeshOmit.exe` build with PyInstaller.
- SQLite storage in WAL mode.
