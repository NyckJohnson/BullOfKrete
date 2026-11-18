"""Chooses one available simulator by name and newest runtime.

`xcrun simctl list devices available -j` lists devices per runtime id
(`com.apple.CoreSimulator.SimRuntime.iOS-18-2`). Only iOS runtimes count; the newest is the
highest numeric version in the id (18-10 beats 18-9). The chosen device's UDID is stored in
`{results}/simulator.txt`, where every gate step reads it.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path

UDID_FILE = "simulator.txt"
"""The file in the results folder holding the chosen simulator's UDID."""

_IOS_RUNTIME = "SimRuntime.iOS-"
_IPHONE = "iPhone"


class SimulatorError(RuntimeError):
    """No simulator could be chosen; the message names the `simulator` setting and the fix."""


def pick(listing: Mapping[str, object], name: str) -> str | None:
    """The UDID of the device called `name` on the newest iOS runtime that has it.

    An empty `name` means the newest available device whose name starts with `iPhone`. Devices
    marked `isAvailable: false` are skipped. None when nothing matches.
    """
    devices = listing.get("devices")
    if not isinstance(devices, Mapping):
        return None
    best: tuple[tuple[int, ...], str] | None = None
    for runtime, entries in devices.items():
        version = _ios_version(str(runtime))
        if version is None or not isinstance(entries, list):
            continue
        for device in entries:
            if not isinstance(device, Mapping) or device.get("isAvailable") is False:
                continue
            device_name = device.get("name")
            udid = device.get("udid")
            if not isinstance(device_name, str) or not isinstance(udid, str):
                continue
            wanted = device_name == name if name else device_name.startswith(_IPHONE)
            # Strictly newer only: the first match on a runtime wins.
            if wanted and (best is None or version > best[0]):
                best = (version, udid)
    return best[1] if best is not None else None


def choose(name: str, results: Path) -> str:
    """Pick the simulator for the `simulator` setting `name` and store its UDID.

    Runs `xcrun simctl list devices available -j`, writes the UDID to `{results}/simulator.txt`
    and returns it. Raises `SimulatorError` when simctl can't run or nothing matches.
    """
    try:
        done = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "available", "-j"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise SimulatorError(
            f"could not run `xcrun simctl` ({exc.strerror or exc}) to choose the simulator "
            "(setting `simulator`): install Xcode and run "
            "`xcode-select -s /Applications/Xcode.app`."
        ) from exc
    if done.returncode != 0:
        raise SimulatorError(
            "`xcrun simctl list devices available -j` failed while choosing the simulator "
            f"(setting `simulator`): {(done.stderr or done.stdout or '').strip()}"
        )
    try:
        listing = json.loads(done.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise SimulatorError(
            f"could not read simctl's device list while choosing the simulator: {exc}"
        ) from exc
    udid = pick(listing if isinstance(listing, dict) else {}, name)
    if udid is None:
        if name:
            wanted = f"no available simulator is named {name!r}"
        else:
            wanted = "no available iPhone simulator was found"
        raise SimulatorError(
            f"{wanted} (setting `simulator`). Set `simulator` to a device listed by "
            "`xcrun simctl list devices available` (empty means the newest iPhone), or add "
            "one in Xcode > Window > Devices and Simulators."
        )
    results.mkdir(parents=True, exist_ok=True)
    (results / UDID_FILE).write_text(udid + "\n", encoding="utf-8")
    return udid


def _ios_version(runtime: str) -> tuple[int, ...] | None:
    """(18, 2) from `…SimRuntime.iOS-18-2`; None for other platforms or unreadable ids."""
    _, found, rest = runtime.partition(_IOS_RUNTIME)
    if not found:
        return None
    try:
        return tuple(int(part) for part in rest.split("-"))
    except ValueError:
        return None
