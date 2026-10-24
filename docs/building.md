# Running from source, building the exe, running the tests

## From source

Python 3.11 or newer (developed with 3.13).

```
git clone https://github.com/opensourcera/MeshOmit.git
cd MeshOmit
pip install -r requirements.txt
meshomit.cmd            Windows
./meshomit.sh           Linux, macOS
```

`requirements.txt`:

| package | why |
|---|---|
| `meshcore` 2.3 or newer | the companion protocol |
| `bleak` 1.0 or newer | Bluetooth LE |
| `textual` 0.80 or newer (tested with 8.x) | the screen |
| `rich` | text styling |
| `pyserial` | serial links |
| `winrt-Windows.Devices.Bluetooth`, `winrt-Windows.Devices.Enumeration`, `winrt-Windows.Foundation` | Windows only, for pairing with a PIN. `winrt-Windows.Devices.Radios` is pulled in by bleak and used to switch the radio on |

The launchers set `PYTHONUTF8=1`, clear `NO_COLOR` and set `COLORTERM=truecolor` before starting
`python -m meshomit`. Without them, a `NO_COLOR` in the environment draws the whole screen in grey.

On Linux, Bluetooth needs BlueZ and the user in the `bluetooth` group (or the usual permissions); serial
needs the `dialout` group.

## The single-file Windows build

```
pip install pyinstaller
build_exe.cmd
```

produces `dist\MeshOmit.exe` (about 36 MB; Python and every library are inside), and copies
`messages.json` and `config.example.json` next to it. Ship the exe with `messages.json`; the first start
writes `config.json` next to the exe. The build takes a minute or two.

The build collects whole packages (`--collect-all textual rich meshcore bleak`) because Textual loads its
CSS and widgets dynamically, and the `winrt` and `serial` submodules because they are imported lazily.
The `winrt.windows.*` namespaces are separate pip packages that PyInstaller's submodule scan does not
walk, so each one bleak touches is named as a `--hidden-import`; without `winrt.windows.foundation.collections`
the exe connects but its Bluetooth scan reports no devices at all (the error only shows with
`MESHOMIT_DEBUG=1`, which writes `meshomit-debug.log`).

## Tests

The tests drive the real screen headlessly with Textual's test pilot and a fake node (`tests/fake_node.py`)
that records what would have been sent. No radio, no Bluetooth.

```
pip install pytest
python -m pytest tests -q
```

or without pytest:

```
python tests/run_all.py
```

They cover: windows and unread counts, the nick list per window, clicking a name in the feed, the input
line and its commands, private messages, the two-word `/msg` name, `/whois`, the `t` key following the
selected window, joining a received invitation with the inviter as creator, and the config being written.
Each test builds its own configuration in a temporary folder from `config.example.json`.

## Code layout and conventions

- `meshomit/core.py` must not import Textual; it talks to the screen only through the `ui` callbacks
  (see [architecture.md](architecture.md)). This keeps the engine testable and lets another front end be
  written.
- All text the bot sends comes from `messages.json`; do not add sentences to the code.
- Device identifiers (Bluetooth addresses, PINs, passwords) live only in `config.json` and the password
  files, both ignored by git.
- Lines are at most 120 characters; `pyflakes meshomit` is clean.
