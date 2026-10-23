# MeshOmit, Copyright (c) 2026 opensourcera. MIT License, see LICENSE.
"""Connect to a MeshCore companion over Bluetooth from Windows: pair with the on-screen PIN first, then connect."""
import asyncio

from bleak import BleakClient
from meshcore import MeshCore
from meshcore.ble_cx import BLEConnection, UART_TX_CHAR_UUID, UART_SERVICE_UUID, UART_RX_CHAR_UUID

from . import pairing
from .connection import PHONE_HINT


class PairingError(Exception):
    pass


async def connect(addr: str, pin: str | None, log, timeout: float = 10.0) -> MeshCore:
    """log(text) receives progress lines. Raises PairingError when the PIN is wrong or missing,
    ConnectionError for everything else."""
    try:
        radio = await pairing.bluetooth_on()
    except Exception as e:
        radio = "unknown"
        log("Bluetooth: could not check the radio (%s)" % str(e)[:60])
    if radio == "turned on":
        log("Bluetooth: the radio was off, switched it on")
        await asyncio.sleep(3)
    elif radio == "none":
        raise ConnectionError("no Bluetooth radio found on this computer (adapter unplugged or driver off)")
    elif radio == "off":
        raise ConnectionError("Bluetooth is switched off: turn it on in Windows Settings > Bluetooth & devices")

    if await pairing.is_paired(addr):
        log("Bluetooth: already paired")
    else:
        if not pin:
            raise PairingError("device is not paired and no PIN was given")
        log("Bluetooth: pairing with PIN...")
        ok, status = await pairing.pair_with_pin(addr, pin)
        if not ok:
            log("Hint: " + PHONE_HINT)
            if "not found" in status.lower():  # off, out of range or held by a phone: retry quietly, the PIN is fine
                raise ConnectionError("node not found: " + status)
            raise PairingError("pairing failed: " + status)
        log("Bluetooth: paired")

    client = BleakClient(addr, timeout=30)
    try:
        await client.connect()
    except Exception as e:
        log("Hint: " + PHONE_HINT)
        raise ConnectionError("node not reachable (%s)" % str(e)[:80])
    conn = BLEConnection(client=client)
    mc = MeshCore(conn, default_timeout=timeout)
    last_err = None
    for attempt in range(3):
        try:
            await client.start_notify(UART_TX_CHAR_UUID, conn.handle_rx)
            last_err = None
            break
        except Exception as e:  # Windows sometimes cancels the first subscribe right after connecting
            last_err = e
            log("Bluetooth: subscribe failed (%s), retrying" % str(e)[:60])
            await asyncio.sleep(2)
    if last_err is not None:
        try:
            await client.disconnect()
        except Exception:
            pass
        if "Unreachable" in str(last_err):
            # A stale bond shows up as "Unreachable": drop it so the next attempt pairs again with the PIN.
            await pairing.unpair(addr)
            raise ConnectionError("stale bond removed, pairing again with the PIN")
        raise ConnectionError("could not subscribe: %s" % last_err)
    try:
        service = client.services.get_service(UART_SERVICE_UUID)
        if service is None:
            raise ConnectionError("this device has no MeshCore serial service (is it a MeshCore node?)")
        conn.rx_char = service.get_characteristic(UART_RX_CHAR_UUID)
        await mc.dispatcher.start()
        mc.connection_manager._is_connected = True
        res = await mc.commands.send_appstart(timeout=5)
        if res is None or res.type.name == "ERROR":
            log("Hint: " + PHONE_HINT)
            raise ConnectionError("node did not answer the app start")
    except Exception as e:  # never leave a connected client behind: Windows would report the node as busy
        for closer in (mc.dispatcher.stop, client.disconnect):
            try:
                await closer()
            except Exception:
                pass
        raise e if isinstance(e, ConnectionError) else ConnectionError("bluetooth: %s" % e)
    mc._link_client = client  # keep a handle for liveness checks
    return mc
