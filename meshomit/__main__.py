# MeshOmit, Copyright (c) 2026 opensourcera. MIT License, see LICENSE.
"""MeshOmit: a MeshCore test-reply bot, beacon sender and repeater logger with a terminal screen.
usage: python -m meshomit [config.json]
Without a config.json the screen opens with a setup form (connection, place names) and writes one."""
import os
import sys

# a stray NO_COLOR (some launchers set it) would draw the whole screen in grey; Textual reads it at import
os.environ.pop("NO_COLOR", None)
os.environ.setdefault("COLORTERM", "truecolor")

from .app import MeshOmitApp, load_config  # noqa: E402


def main():
    if os.environ.get("MESHOMIT_DEBUG"):  # a file log of the Bluetooth stack next to the config
        import logging
        logging.basicConfig(filename=os.path.join(os.getcwd(), "meshomit-debug.log"), level=logging.DEBUG,
                            format="%(asctime)s %(name)s %(levelname)s %(message)s")
    if getattr(sys, "frozen", False):  # MeshOmit.exe: config and messages live next to the exe
        here = os.path.dirname(os.path.abspath(sys.executable))
    else:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "config.json")
    cfg = load_config(cfg_path)
    MeshOmitApp(cfg, cfg_path).run()


if __name__ == "__main__":
    main()
