# MeshOmit user guide

MeshOmit is a terminal program. It needs a terminal with 24-bit colour and mouse support: Windows
Terminal on Windows (not the old console window), any modern terminal on Linux and macOS. A window of
at least 120 columns by 40 rows is comfortable.

## 1. Starting

```
meshomit.cmd                Windows, from the folder of the program
./meshomit.sh               Linux and macOS
python -m meshomit          any system, from the folder of the program
python -m meshomit other.json   with another settings file
MeshOmit.exe                the single-file Windows build; double-click it
```

Without a `config.json` next to the program (next to the exe for the single-file build) a setup form
opens:

1. **Connection**. *Bluetooth LE*: press *Scan for devices*; the node must be switched on and must not be
   connected to a phone (a node that is connected to a phone stops advertising and is invisible). MeshCore
   nodes are listed first; pick yours, or type its address. *USB serial*: pick the port from the list.
   *WiFi / TCP*: host and port of a node with the TCP companion build.
2. **Where you are**: a few place names separated by commas. The bot uses one at random each time it
   speaks ("Springfield", "Downtown", "Riverside"), so it does not sound like a machine.
3. **Your node's name**: optional. Normally the program takes it from the node after connecting.

*Save and start* writes `config.json` and connects. A Bluetooth node that is not paired yet asks for the
six-digit PIN shown on its screen; the PIN is saved and asked again only when the node has changed it
(it changes when the node reboots on most boards).

The first lines in the feed explain the keys. The program starts in **Operator mode**: it listens and
shows everything, and says nothing by itself until you switch the bot on.

## 2. The screen

```
 ┌─ window title ──────────────────────────┐ ┌─ Status ─────────┐
 │ the feed: one line per message           │ │ mode, node, link │
 │                                          │ │ counters, timers │
 │                                          │ ├─ Windows (1-9) ──┤
 │                                          │ │ All, channels,   │
 │                                          │ │ rooms, privates  │
 │                                          │ ├─ Nicks (3 h) ────┤
 │                                          │ │ who spoke here   │
 │                                          │ ├─ Repeaters ──────┤
 │                                          │ ├─ Events ─────────┤
 └──────────────────────────────────────────┘ │ what happened    │
  #test  the input line_                      └──────────────────┘
  key help
```

**The feed.** Each line shows the time, the channel, `<sender>` in a colour that stays the same for that
station, and the text, followed by the hops and SNR of the strongest copy heard ("(2h +5.5dB via
Hilltop>Ridge)"). Lines are styled by kind:

| look | meaning |
|---|---|
| white text | a message received |
| dimmed | a message that was queued on the node before the program started (never answered) |
| yellow text | a test call the bot would answer |
| black on yellow | someone named your node (`@[YourNode]`) |
| `* YourNode text` in purple | a beacon your bot sent |
| bright white `<YourNode>` | your own messages and the bot's answers |
| black on lilac | a direct message received (encrypted, only you can read it) |
| lilac `-> name:` | a direct message you sent |
| green `***` | lines from the program itself |

**Status.** The mode (BOT in blue, OPERATOR in lilac), the node's name, the link, how long it has been
connected, the number of contacts the node knows, the counters since start, the time of the next beacon
and the next repeater poll.

**Windows.** One entry per channel the node listens to, one per room you created or joined, one per
private conversation. The number in front is the key that selects it. A count in brackets is the number
of unread messages in that window. A room shows its creator after a `*`. A private window shows `->` and
the person's name.

**Nicks.** Who spoke in the selected window during the last 3 hours, most recent first, with how far away
(direct or N hops), how many messages, and, when both nodes advertise a position, the distance and
direction ("8.0km W"). The creator of a room heads its list with a `*`. In the *All* window the list
covers everything.

**Repeaters.** The last poll of each configured repeater: battery, uptime, noise floor, trace SNR, time.

**Events.** What the program did and any problem: connection steps, contacts loaded, beacons sent, the
reason the bot stayed quiet, invitations received, repeater results.

The whole screen turns **lilac** in Operator mode and **blue** in Bot mode, so the mode is visible from
across the room.

## 3. The input line

The line under the feed is where you type, like the box under a channel in mIRC. The label in front of it
names where Enter sends:

| label | Enter sends to |
|---|---|
| `#test`, `Public`, `#mytown` | that channel or room (the window you are looking at) |
| `All -> #test` | the beacon channel, when the *All* window is selected |
| `<K1ABC>` | a direct message to that person, encrypted for them |

Enter sends and clears the line. The line takes up to 140 characters. Enter on an **empty** line opens
the big send window (section 5). The input line has the focus from the start and gets it back after
every dialog.

While the input line has the focus, letters are text: the single-key shortcuts of section 7 do not
fire. Press **Escape** to leave the line (the keys work again), **Enter** to come back to it. The slash
commands below do everything the keys do, so you rarely need to leave the line.

### Commands

| command | what it does |
|---|---|
| `/help` | lists the commands |
| `/w 4`, `/4` | selects window 4 |
| `/query Name` | opens a private window with that contact (`/q`, `/pm` work too) |
| `/msg Name text` | sends a direct message without changing window; names with spaces work, the longest leading words that name a contact exactly are used |
| `/whois Name` | what the node knows about a contact (section 8); a part of the name is enough (`/who`, `/where`, `/loc`) |
| `/reply`, `/reply Name` | answer the last test call (or that station's last message) by hand, see "Answering a test yourself" below |
| `/bot`, `/op` | switch the bot on or off (`/mode` toggles) |
| `/join` | opens the room window (section 6) |
| `/send` | opens the big send window |
| `/dash` | opens the dashboard (section 9) |
| `/beacon` | sends a beacon now |
| `/test` | sends "Test" to the window you are looking at |
| `/poll` | polls the repeaters now |
| `/pause` | pauses or resumes the bot's answers without leaving Bot mode |
| `/quit` | quits |

Anything else starting with `/` prints "Unknown command".

## 4. Windows and private conversations

Select a window with its number (after Escape), by clicking it in the *Windows* list, or with `/w N`.
The feed then shows only that window, with its name as the title, and the nick list shows who spoke
there. Window 1, *All*, shows everything in one stream.

**Private conversations** are MeshCore direct messages: encrypted with the other person's public key,
readable only by the two of you. They need the person to be in your node's contact list, which the
program loads shortly after connecting (about a minute with a few hundred contacts; the status panel
shows the count). To open one:

- click a nick in the *Nicks* list;
- click a `<name>` in the feed (it lights up under the mouse);
- type `/query Name`.

A new private window opens, is selected, and the input line shows `<Name>`. Type and press Enter. An
incoming direct message opens its private window by itself and counts as unread until you look at it.

When the person is **not** in the contact list (a station you only heard on a channel), a click on the
name cannot open a private window. Instead the program selects the channel the message came from and
types `@[Name] ` in the input line for you: a mention, which the MeshCore apps show highlighted to that
person. Finish the sentence and press Enter.

The nick list and the names in the feed tell you nothing about who is online; the mesh has no presence.
They tell you who was heard, and when.

### Answering a test yourself

In Operator mode the bot is silent, but you can still answer a test call in two key presses. `/reply`
in the input line, or the `a` key when the line is not focused, selects the channel the last test came
from and puts a factual answer in the input line:

```
@[K1ABC] got you 2 hops via Hilltop>Ridge here in Springfield, +7.5 dB
```

The station is named with a mention, the hop count and the repeaters come from the strongest copy your
node heard, the SNR too, and the place is `operator_location` from `config.json` (or the first of your
`locations`). Read it, change anything, press Enter. Nothing is sent until you do. `/reply Name` prepares
the same answer to that station's last message, test or not. The wording comes from the
`operator_replies` list in `messages.json`; these lines skip the human pass, so they are sent exactly as
written.

### Fields in your own messages

While typing, in the input line or in the big send window, type `{` and a list opens:

| field | filled in with |
|---|---|
| `{name}` | the station you address |
| `{hops}` | hops of its last message ("direct, no repeater", "3 hops") |
| `{via}` | the repeaters it came through ("via Hilltop>Ridge", or "direct") |
| `{snr}`, `{rssi}` | SNR in dB and RSSI in dBm of its last message |
| `{heard}` | when its last message was heard |
| `{location}` | your place, `operator_location` in `config.json` |
| `{time}` | the time now |
| `{me}` | your node's name |

Below the fields the same list offers the emoticons of `messages.json`, drawn as the picture they stand
for (a smiling face, a waving hand, a heart...) and inserted as their text form, `:)` `o/` `<3`, which every
mesh device can show. Pick one with Enter (or click), Escape closes the list and leaves the `{` typed. The
list shows the value each field would take right now. The fields are replaced when you press Enter to send, so you see
`@[K1ABC] got you {hops} {via}, {location}` while typing and the mesh sees
`@[K1ABC] got you 2 hops via Hilltop>Ridge, Springfield`.

Which station the fields refer to: the one you address with `@[name]` at the start of the message, using
its last message; without a mention, the last message received in the window you are looking at; failing
that, the last test call heard. A `{word}` that is not a field is sent as typed.

## 5. The big send window

Enter on an empty input line, `/send`, or the *Enter* key when the input line is not focused. It is a
pop-up with:

- **To**: any channel the node listens to, any room, and, as "DM name", anyone in the contact list.
  It is preset to the window you are looking at;
- a text box with a `n/140` counter;
- buttons that insert an ASCII emoticon (`:)` `;)` `:D` `:P` `:(` `<3` `o/` `^^` `73` `+1`);
- a list of ready-made lines ("Test", "hi all, anyone around?", "copy, thanks", "73"...). Click one or
  move to it and press Enter to put it in the text box.

Enter sends, Escape cancels. The emoticons and the ready-made lines come from `messages.json` (lists
`emoticons` and `quick`).

Everything you send is just text to the other side: they see `YourNode: text` in their app, with the
usual MeshCore formatting. The `<` `>` around names exist only on your screen.

## 6. Rooms and invitations

A room is a MeshCore channel. `/join` or the `j` key opens the room window.

- A name starting with `#` (for example `#mytown`) makes a **hashtag room**: the key is derived from the
  name, so anyone who adds a channel with exactly that name in their MeshCore app is in. Easy to join,
  private only as long as the name is not guessed.
- A name without `#` makes a **private room**: a random 16-byte key is generated. The invitation carries the
  key in hex and the other side adds a channel with that name and key.

Type part of a contact's name in the search box, pick the people to invite from the list, and press
*Join room and send invites*. The program:

1. programs the channel into the node, in the first free of its 8 channel slots (a slot the node already
   uses for a channel you did not list is kept and listened to as well);
2. adds the room to `config.json` so it is listened to next time, with you as its creator;
3. opens the room's window and selects it;
4. sends each invited person a direct message: "join me on channel #name (add it as a channel with that
   exact name)" or "join me on channel name, key 0123…".

**Joining** does not announce anything on the channel. MeshCore has no join or presence message; people
notice you when you write.

**Received invitations.** When someone sends you such a direct message, the events panel says "Alice
invites you to #mytown (press j to join)". The room window then opens with the name and the key already
filled in; press the button and you are in. The inviter is shown as the room's creator, after a `*` in the
window list and at the head of the nick list of that room.

## 7. Keys

These work when the input line does not have the focus (press Escape first):

| key | action |
|---|---|
| `1`..`9` | select that window |
| `Enter` | back to the input line |
| `m` | switch between Bot mode (blue) and Operator mode (lilac) |
| `j` | room window |
| `d` | dashboard (Escape or `d` closes it) |
| `b` | send a beacon now |
| `t` | send "Test" to the window you are looking at (the beacon channel in the *All* window) |
| `a` | answer the last test call by hand (`/reply`) |
| `r` | poll the repeaters now |
| `p` | pause or resume the bot's answers |
| `q` | quit |

Clicking works everywhere: windows, nicks, names in the feed, buttons and lists in the dialogs.

## 8. Who and where: `/whois`

`/whois Name` prints what your node's contact list knows about a station:

```
*** K1ABC: companion, last advert 25 min ago, 2 hops, at 39.7817, -89.6501 (8.0 km W of MyNode)
    map: https://www.openstreetmap.org/?mlat=39.78170&mlon=-89.65010&zoom=13
```

- the type: companion (a person's node), repeater, room server or sensor;
- when its last advert was heard and how many hops away it is;
- its position, when the owner set one on their node: MeshCore nodes include their latitude and longitude
  in their adverts. Channel messages carry no position; only adverts do;
- the distance and compass direction from your node, when your own node has a position (set it in the
  MeshCore phone app);
- a map link. In Windows Terminal, Ctrl+click opens it.

Stations whose owners did not set a position show "No position in its advert". The nick list shows the
same distance as a short tag after each name, refreshed every 30 seconds.

## 9. The two modes

**Operator mode** (lilac). The program is a chat client. It listens on every channel, stores everything,
shows everything, polls the repeaters, but never speaks by itself. This is how it starts.

**Bot mode** (blue). `m` or `/bot`. In addition to the above the bot:

- answers test calls ("test", "ping", "radio check", the list is configurable) on the configured channels
  with a line from `messages.json`, naming the station with `@[name]` so the MeshCore apps highlight it.
  Each station gets every line once before any line repeats. One answer per station per 10 minutes, at
  most 6 an hour, 2 to 6 seconds after the call, never to a station whose name contains "bot", and now
  and then just "brb". Every line goes through the human pass (short words, the odd typo);
- optionally answers people who mention it with `@[YourNode]` without a test word;
- sends a beacon every 10 minutes ("hi all, MyNode in Downtown, who hears me?") and counts every
  message that names it within 10 minutes as a reply to that beacon.

`p` or `/pause` keeps Bot mode but stops the answers; `/op` or `m` goes back to Operator mode. Messages
queued on the node before the program started are shown dimmed and never answered.

All the limits are in `config.json` and all the texts in `messages.json`; see
[configuration.md](configuration.md).

## 10. The dashboard

`d` or `/dash`. Four cards (Heard, Tests, Beacons, Repeaters) for the last 24 hours and all time, four
sparklines per hour (messages heard, tests heard, our answers, beacon replies), and tables: the stations
heard most with hops and SNR, which repeater the packets came through and its share, how many hops away
people are, the last ten beacons with their reply counts, the last repeater polls, our last answers.
It refreshes every 30 seconds. Escape or `d` closes it.

## 11. Repeaters

With repeaters configured (see [configuration.md](configuration.md)), every 30 minutes and on `r` or
`/poll` the program, for each repeater:

1. sends a trace through it and records the SNR there and back;
2. logs in with the admin password read from a file (never stored in `config.json`), asks for the status
   and records battery, uptime, noise floor, last RSSI, packet counters, air time, queue length;
3. asks for the neighbour list and records each neighbour with its age and SNR.

The Repeaters panel shows the latest readings, the dashboard the history, and the events panel one line
per poll ("Ridge: 4.09 V, up 44.4 h, noise -117, trace 13.25/9.25").

## 12. The data

Everything is in `meshomit.sqlite` next to `config.json`, in WAL mode, so you can query it while the
program runs. The tables are described in [architecture.md](architecture.md). A few queries:

```
sqlite3 meshomit.sqlite "select datetime(ts,'unixepoch','localtime'), sender, text from messages where is_trigger=1 order by ts desc limit 20"
sqlite3 meshomit.sqlite "select datetime(ts,'unixepoch','localtime'), text, replies from beacons order by ts desc"
sqlite3 meshomit.sqlite "select last_hop, count(*) from rx_packets where ts > strftime('%s','now')-3600 group by last_hop"
```
