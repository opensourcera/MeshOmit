# Troubleshooting

**Everything is grey.** The terminal is not showing 24-bit colour. On Windows use Windows Terminal, not the
old console window ("Command Prompt" without tabs). Make sure `NO_COLOR` is not set in the environment;
the launchers clear it, a bare `python -m meshomit` does not. `COLORTERM=truecolor` helps on some
terminals.

**The node is not in the scan, or "node not reachable".** A node accepts one Bluetooth link at a time,
and while a phone holds it the node stops advertising. Disconnect the node in the MeshCore phone app, or
switch the phone's Bluetooth off, and press *Scan again* or let the program reconnect. The program keeps retrying every 10 s and
prints this hint in the events panel. Another copy of MeshOmit, or another companion program, has the same
effect.

**The scan finds no devices at all, not even headphones or a TV.** Bluetooth is off in Windows, or the
program could not reach the Windows Bluetooth stack. Set `MESHOMIT_DEBUG=1` in the terminal before starting
and look at `meshomit-debug.log` in the working folder: a `ModuleNotFoundError` there means a broken build
of the exe (see `docs/building.md`); run from source with `meshomit.cmd` in the meantime.

**Bluetooth is off.** On Windows the program switches the radio on by itself. If Windows refuses (some
corporate policies), switch it on in Settings > Bluetooth & devices. "No Bluetooth radio found" means the
adapter is unplugged or its driver is off.

**It keeps asking for the PIN.** The PIN changes when the node reboots on most boards; read the six digits
on the node's screen again. If the node shows no PIN, the companion firmware may be built without a PIN;
then type any six digits. A stale pairing in Windows is removed by the program when it sees "Unreachable",
after which the next attempt pairs again; you can also remove the node in Settings > Bluetooth & devices.

**"Contacts: none received".** Normal right after connecting on some boards; the program sends a fresh app
start and tries again 30 s later, and the list arrives on the second try ("Contacts: 350 known to the
node"). Until then private windows and `/whois` say the person is not in the list.

**No messages arrive, although the node shows them.** Check `rx_packets` in the database: if decrypted
channel texts are being recorded, the radio hears them and the node decrypts them, and only the fetch
is stuck. `pull_loop` asks for queued messages every 20 s and should get them within that time, logging
"Pulled N queued messages". If nothing comes for minutes, restart the program; if it persists, the node's
queue may be held by another client (see the phone hint above).

**The bot does not answer a test.** Look at the events panel: it says why ("in operator mode", "paused",
"not answering X again yet", "hourly reply limit reached"). Also check that the message arrived on a
channel listed in `bot.reply_channels`, that the whole message is one of `bot.triggers`, that the sender's
name does not contain a word from `bot.ignore_senders_containing`, and that the message is not dimmed
(backlog from before the start).

**Keys do nothing.** The input line has the focus, so letters are typed into it. Press Escape, then the
key. Or use the slash commands.

**The window list highlights an entry but the feed does not change.** Moving in the list with the arrow
keys only highlights. Press Enter on the entry, click it, or press its number.

**Serial: "could not open port".** Another program holds the port (a serial monitor, the MeshCore web
client, a flasher). Close it. On Linux add your user to the `dialout` group.

**The repeater says "node refused the login".** The node sends a login through its own contact
entry for the repeater, so a node that never received the repeater's advert cannot log in, even though
the trace works (a trace needs only the hash). Wait for the advert (repeaters send one every few hours;
most can be told to send one now from their console) and `/add` it, or leave contacts in automatic mode
so the node keeps it by itself. A node you just switched to is the usual case.

**The repeater says "no login answer".** The password file is wrong, the node's clock was off (the program
sets it when more than 30 s off; wait for the next poll), or the repeater is out of reach right now. The
trace SNR in the same row tells you whether it heard the trace.

**`config.json` was written with a BOM or odd encoding.** Both files are read as UTF-8 with an optional
byte-order mark; any editor's default works.

**The program crashed with a traceback.** Open an issue with the traceback and the last lines of the events
panel (the `events` table in the database holds them). Remove your Bluetooth address, PIN and any password
first.
