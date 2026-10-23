# Credits

MeshOmit is written by opensourcera and released under the MIT License (see `LICENSE`).
It stands on the work of the people and projects below. Thank you.

## The mesh

- **MeshCore** firmware and protocol by Scott Powell and the MeshCore contributors,
  https://github.com/ripplebiz/MeshCore (MIT). MeshOmit talks to a node running the
  MeshCore *companion* firmware; the channels, adverts, direct messages, repeater login,
  status and trace commands used here are all MeshCore features.
- The **MeshCore companion protocol** documentation and the behaviour of the reference
  phone and web apps guided the room and invite conventions used in MeshOmit.

## Python libraries

| library | authors | licence | used for |
|---|---|---|---|
| [meshcore](https://github.com/fdlamotte/meshcore_py) (meshcore_py) | Florent de Lamotte, Alex Wolden and contributors | MIT | the companion protocol: connection, commands, events, contact list |
| [Textual](https://github.com/Textualize/textual) | Will McGugan and Textualize | MIT | the terminal user interface (screens, widgets, mouse support) |
| [Rich](https://github.com/Textualize/rich) | Will McGugan and Textualize | MIT | coloured text, links and tables inside Textual |
| [bleak](https://github.com/hbldh/bleak) | Henrik Blidh and contributors | MIT | Bluetooth Low Energy on Windows, Linux and macOS |
| [pywinrt](https://github.com/pywinrt/pywinrt) (`winrt-*` packages) | David Lechner and contributors | MIT | Bluetooth pairing with a PIN and switching the radio on, on Windows |
| [pyserial](https://github.com/pyserial/pyserial) | Chris Liechti and contributors | BSD-3-Clause | USB serial links and listing the serial ports |
| [PyInstaller](https://www.pyinstaller.org/) | Hartmut Goebel, Giovanni Bajo, David Vierra, David Cortesi, Martin Zibricky and contributors | GPL-2.0-or-later with the bootloader exception | building the single-file `MeshOmit.exe` (optional, build time only) |
| Python and its standard library (`asyncio`, `sqlite3`, `json`, `zlib`...) | the Python Software Foundation | PSF | everything else |

The licences of these projects apply to their own code. They are not changed by the MIT
licence of MeshOmit, and nothing from them is redistributed in this repository except
through the normal `pip install` of the packages listed in `requirements.txt`.

## Ideas borrowed

- The window list, nick list, `<name>` lines, input line with a target label and the
  `/command` syntax follow the classic IRC clients, mIRC in particular.
- The "human pass" (short words, the odd typo) was inspired by how people actually type
  on a small mesh keyboard.
- OpenStreetMap, https://www.openstreetmap.org, is used for the map links printed by
  `/whois` (data © OpenStreetMap contributors, ODbL).
