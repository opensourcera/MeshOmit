# MeshOmit, Copyright (c) 2026 opensourcera. MIT License, see LICENSE.
"""Windows Bluetooth pairing with a PIN (passkey entry) through the Windows runtime, and unpairing.
bleak's own pair() cannot supply a PIN, so this talks to the runtime directly. Windows only."""
import sys


def _winrt():
    from winrt.windows.devices.bluetooth import BluetoothLEDevice
    from winrt.windows.devices.enumeration import (DevicePairingKinds, DevicePairingProtectionLevel,
                                                   DevicePairingResultStatus)
    return BluetoothLEDevice, DevicePairingKinds, DevicePairingProtectionLevel, DevicePairingResultStatus


def _addr_int(addr: str) -> int:
    return int(addr.replace(":", "").replace("-", ""), 16)


async def is_paired(addr: str) -> bool:
    BluetoothLEDevice, *_ = _winrt()
    dev = await BluetoothLEDevice.from_bluetooth_address_async(_addr_int(addr))
    return bool(dev and dev.device_information.pairing.is_paired)


async def pair_with_pin(addr: str, pin: str) -> tuple[bool, str]:
    """Returns (ok, status text). Status names come from the Windows DevicePairingResultStatus enum."""
    if sys.platform != "win32":
        return False, "PIN pairing is implemented for Windows only"
    BluetoothLEDevice, Kinds, Level, Status = _winrt()
    dev = await BluetoothLEDevice.from_bluetooth_address_async(_addr_int(addr))
    if dev is None:
        return False, "device not found (is it advertising?)"
    info = dev.device_information
    if info.pairing.is_paired:
        return True, "already paired"
    custom = info.pairing.custom

    def handler(sender, args):
        if args.pairing_kind == Kinds.PROVIDE_PIN:
            args.accept_with_pin(pin)
        else:
            args.accept()

    token = custom.add_pairing_requested(handler)
    try:
        res = await custom.pair_with_protection_level_async(
            Kinds.PROVIDE_PIN | Kinds.CONFIRM_ONLY | Kinds.CONFIRM_PIN_MATCH, Level.ENCRYPTION_AND_AUTHENTICATION)
        ok = res.status == Status.PAIRED
        name = next((k for k, v in Status.__dict__.items() if v == res.status), str(res.status))
        return ok, name.lower().replace("_", " ")
    finally:
        custom.remove_pairing_requested(token)


async def unpair(addr: str) -> bool:
    BluetoothLEDevice, *_ = _winrt()
    dev = await BluetoothLEDevice.from_bluetooth_address_async(_addr_int(addr))
    if dev is None or not dev.device_information.pairing.is_paired:
        return True
    res = await dev.device_information.pairing.unpair_async()
    return res.status == 0


async def bluetooth_on() -> str:
    """Make sure the Bluetooth radio is on. Returns "on", "turned on", "off" (could not switch it) or "none"."""
    from winrt.windows.devices.radios import Radio, RadioAccessStatus, RadioKind, RadioState
    radios = await Radio.get_radios_async()
    bt = [r for r in radios if r.kind == RadioKind.BLUETOOTH]
    if not bt:
        return "none"
    if any(r.state == RadioState.ON for r in bt):
        return "on"
    if await Radio.request_access_async() != RadioAccessStatus.ALLOWED:
        return "off"
    for r in bt:
        if await r.set_state_async(RadioState.ON) == RadioAccessStatus.ALLOWED:
            return "turned on"
    return "off"
