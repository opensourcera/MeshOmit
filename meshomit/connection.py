# MeshOmit, Copyright (c) 2026 opensourcera. MIT License, see LICENSE.
"""Links to a MeshCore companion node: Bluetooth LE, USB serial or TCP (WiFi).

config["connection"] = {"type": "ble",    "address": "AA:BB:CC:DD:EE:FF", "pin": null}
                     | {"type": "serial", "port": "COM6", "baud": 115200}
                     | {"type": "tcp",    "host": "192.168.1.50", "port": 5000}
"""
import asyncio
import sys

from meshcore import MeshCore


PHONE_HINT = ("a node takes one Bluetooth link at a time. If the MeshCore app on a phone (or another program) "
              "is connected to it, disconnect it there; this program keeps retrying by itself.")


class PairingError(Exception):
    """Bluetooth pairing needs a (new) PIN."""


async def connect(conn_cfg: dict, pin: str | None, log, timeout: float = 10.0) -> MeshCore:
    """Open the link described by conn_cfg and finish the app handshake. log(text) gets progress lines.
    Raises PairingError when Bluetooth pairing needs a PIN, ConnectionError for everything else."""
    kind = (conn_cfg.get("type") or "ble").lower()
    if kind == "ble":
        return await connect_ble(conn_cfg["address"], pin, log, timeout)
    if kind == "serial":
        return await connect_serial(conn_cfg["port"], int(conn_cfg.get("baud", 115200)), log, timeout)
    if kind == "tcp":
        return await connect_tcp(conn_cfg["host"], int(conn_cfg.get("port", 5000)), log, timeout)
    raise ConnectionError("unknown connection type '%s' (use ble, serial or tcp)" % kind)


async def connect_serial(port: str, baud: int, log, timeout: float) -> MeshCore:
    log("Serial: opening %s at %d" % (port, baud))
    try:
        mc = await MeshCore.create_serial(port, baud, default_timeout=timeout)
    except Exception as e:
        raise ConnectionError("serial: %s" % e)
    mc._link_client = None
    return mc


async def connect_tcp(host: str, port: int, log, timeout: float) -> MeshCore:
    log("TCP: connecting to %s:%d" % (host, port))
    try:
        mc = await MeshCore.create_tcp(host, port, default_timeout=timeout)
    except Exception as e:
        raise ConnectionError("tcp: %s" % e)
    mc._link_client = None
    return mc


async def connect_ble(addr: str, pin: str | None, log, timeout: float) -> MeshCore:
    if sys.platform == "win32":
        from . import ble
        try:
            return await ble.connect(addr, pin, log, timeout)
        except ble.PairingError as e:
            raise PairingError(str(e))
    # Other systems: bleak pairs through the OS agent; the PIN, when asked, is typed in the OS dialog.
    log("Bluetooth: connecting to %s" % addr)
    try:
        mc = await MeshCore.create_ble(addr, pin=pin, default_timeout=timeout)
    except Exception as e:
        log("Hint: " + PHONE_HINT)
        raise ConnectionError("bluetooth: %s" % e)
    mc._link_client = None
    return mc


def is_alive(mc: MeshCore) -> bool:
    client = getattr(mc, "_link_client", None)
    if client is not None:
        return bool(client.is_connected)
    try:
        return bool(mc.is_connected)
    except Exception:
        return True


async def scan_ble(seconds: float = 6.0) -> list[tuple[str, str]]:
    """(name, address) of the Bluetooth LE devices in range, MeshCore nodes first."""
    from bleak import BleakScanner
    if sys.platform == "win32":
        from . import pairing
        try:
            if await pairing.bluetooth_on() == "turned on":
                await asyncio.sleep(3)
        except Exception:
            pass
    found = await BleakScanner.discover(timeout=seconds)
    rows = []
    for d in found:
        name = d.name or ""
        rows.append((name, d.address))
    rows.sort(key=lambda r: (0 if "meshcore" in r[0].lower() else 1 if r[0] else 2, r[0].lower()))
    return rows


def serial_ports() -> list[tuple[str, str]]:
    """(port, description) of the serial ports on this machine."""
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    return [(p.device, p.description or "") for p in list_ports.comports()]
