"""Tests for `bull.Modules.stack_ios.ios.simulator`.

Choices where the spec is open (the code must match these):
- `simulator.pick(listing, name) -> str | None`: pure; `listing` is the parsed JSON of
  `xcrun simctl list devices available -j` (`{"devices": {<runtime id>: [{udid, name,
  isAvailable, ...}]}}`). Only iOS runtimes count; the newest runtime is the highest numeric
  version in the id (`...SimRuntime.iOS-18-2`, so 18-10 beats 18-9); devices with
  `isAvailable: false` are skipped; a named device matches by exact name; an empty name means
  the newest available device whose name starts with `iPhone`. No match returns None.
- `simulator.choose(name, results) -> str`: runs `xcrun simctl list devices available -j`
  through `subprocess.run` (stdout text), writes the UDID to `{results}/simulator.txt`, returns
  it; no match raises `simulator.SimulatorError` (a `RuntimeError`) whose message contains
  `simulator` (the setting's name).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from bull.Modules.stack_ios.ios import simulator

_RT = "com.apple.CoreSimulator.SimRuntime."


def _dev(udid: str, name: str, available: bool = True) -> dict[str, Any]:
    return {
        "udid": udid,
        "name": name,
        "isAvailable": available,
        "state": "Shutdown",
    }


def _listing(**runtimes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"devices": {_RT + k.replace("_", "-"): v for k, v in runtimes.items()}}


def test_named_device_is_picked_by_name() -> None:
    listing = _listing(
        iOS_18_2=[_dev("A", "iPhone 16"), _dev("B", "iPhone 16 Pro")],
    )
    assert simulator.pick(listing, "iPhone 16 Pro") == "B"


def test_named_device_on_several_runtimes_takes_the_newest_runtime() -> None:
    listing = _listing(
        iOS_17_5=[_dev("OLD", "iPhone 16")],
        iOS_18_2=[_dev("NEW", "iPhone 16")],
    )
    assert simulator.pick(listing, "iPhone 16") == "NEW"


def test_runtime_versions_compare_numerically() -> None:
    listing = _listing(
        iOS_18_9=[_dev("NINE", "iPhone 16")],
        iOS_18_10=[_dev("TEN", "iPhone 16")],
    )
    assert simulator.pick(listing, "iPhone 16") == "TEN"


def test_named_device_only_on_an_older_runtime_is_still_found() -> None:
    listing = _listing(
        iOS_17_5=[_dev("OLD", "iPhone 15")],
        iOS_18_2=[_dev("NEW", "iPhone 16")],
    )
    assert simulator.pick(listing, "iPhone 15") == "OLD"


def test_unavailable_devices_are_skipped() -> None:
    listing = _listing(
        iOS_18_2=[_dev("GONE", "iPhone 16", available=False)],
        iOS_17_5=[_dev("OK", "iPhone 16")],
    )
    assert simulator.pick(listing, "iPhone 16") == "OK"


def test_unknown_name_returns_none() -> None:
    listing = _listing(iOS_18_2=[_dev("A", "iPhone 16")])
    assert simulator.pick(listing, "iPhone 99") is None


def test_name_matches_exactly_not_by_prefix() -> None:
    listing = _listing(iOS_18_2=[_dev("A", "iPhone 16 Pro")])
    assert simulator.pick(listing, "iPhone 16") is None


def test_empty_listing_returns_none() -> None:
    assert simulator.pick({"devices": {}}, "") is None
    assert simulator.pick({"devices": {}}, "iPhone 16") is None


def test_empty_name_picks_the_newest_available_iphone() -> None:
    listing = _listing(
        iOS_17_5=[_dev("OLD", "iPhone 15")],
        iOS_18_2=[_dev("NEW", "iPhone 16")],
    )
    assert simulator.pick(listing, "") == "NEW"


def test_empty_name_ignores_ipads_on_a_newer_runtime() -> None:
    listing = _listing(
        iOS_17_5=[_dev("PHONE", "iPhone 15")],
        iOS_18_2=[_dev("PAD", "iPad Pro 13-inch")],
    )
    assert simulator.pick(listing, "") == "PHONE"


def test_empty_name_ignores_non_ios_runtimes() -> None:
    listing = {
        "devices": {
            _RT + "iOS-17-5": [_dev("PHONE", "iPhone 15")],
            _RT + "watchOS-11-0": [_dev("WATCH", "iPhone Companion")],
        }
    }
    assert simulator.pick(listing, "") == "PHONE"


def test_empty_name_with_only_ipads_returns_none() -> None:
    listing = _listing(iOS_18_2=[_dev("PAD", "iPad Air")])
    assert simulator.pick(listing, "") is None


def test_empty_name_skips_unavailable_iphones() -> None:
    listing = _listing(
        iOS_18_2=[_dev("GONE", "iPhone 16", available=False)],
        iOS_17_5=[_dev("OK", "iPhone 15")],
    )
    assert simulator.pick(listing, "") == "OK"


# --- choose: runs simctl and stores the UDID ----------------------------------------------


def _fake_simctl(
    monkeypatch: pytest.MonkeyPatch, listing: dict[str, Any]
) -> list[list[str]]:
    calls: list[list[str]] = []

    def run(args: Any, *a: object, **kw: object) -> subprocess.CompletedProcess[str]:
        argv = [str(x) for x in args]
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, json.dumps(listing), "")

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_choose_asks_simctl_for_available_devices_as_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_simctl(monkeypatch, _listing(iOS_18_2=[_dev("A", "iPhone 16")]))
    simulator.choose("iPhone 16", tmp_path)
    assert len(calls) == 1
    i = calls[0].index("simctl")
    assert calls[0][i:] == ["simctl", "list", "devices", "available", "-j"]


def test_choose_returns_and_stores_the_udid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = tmp_path / "results"
    results.mkdir()
    _fake_simctl(monkeypatch, _listing(iOS_18_2=[_dev("UDID-1", "iPhone 16")]))
    assert simulator.choose("iPhone 16", results) == "UDID-1"
    assert (results / "simulator.txt").read_text().strip() == "UDID-1"


def test_choose_with_empty_setting_uses_the_newest_iphone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = tmp_path / "results"
    results.mkdir()
    listing = _listing(
        iOS_17_5=[_dev("OLD", "iPhone 15")], iOS_18_2=[_dev("NEW", "iPhone 16")]
    )
    _fake_simctl(monkeypatch, listing)
    assert simulator.choose("", results) == "NEW"
    assert (results / "simulator.txt").read_text().strip() == "NEW"


def test_choose_with_no_match_raises_naming_the_setting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results = tmp_path / "results"
    results.mkdir()
    _fake_simctl(monkeypatch, _listing(iOS_18_2=[_dev("A", "iPhone 16")]))
    with pytest.raises(simulator.SimulatorError, match="simulator"):
        simulator.choose("iPhone 99", results)
    assert not (results / "simulator.txt").exists()


# --- coverage triage -----------------------------------------------------------------------


@pytest.mark.parametrize("listing", [{}, {"devices": []}, {"devices": "none"}])
def test_pick_without_a_devices_mapping_is_none(listing: dict[str, Any]) -> None:
    assert simulator.pick(listing, "iPhone 16") is None


def test_pick_skips_devices_with_a_non_string_name_or_udid() -> None:
    listing = _listing(
        iOS_18_2=[
            {"udid": "X", "name": 5, "isAvailable": True},
            {"udid": None, "name": "iPhone 16", "isAvailable": True},
            _dev("GOOD", "iPhone 16"),
        ]
    )
    assert simulator.pick(listing, "iPhone 16") == "GOOD"
    assert simulator.pick(listing, "") == "GOOD"


def test_pick_skips_a_runtime_whose_version_cannot_be_read() -> None:
    listing = _listing(
        iOS_x=[_dev("BAD", "iPhone 16")], iOS_17_5=[_dev("OK", "iPhone 16")]
    )
    assert simulator.pick(listing, "iPhone 16") == "OK"


def _simctl_result(
    monkeypatch: pytest.MonkeyPatch, rc: int, out: str, err: str = ""
) -> None:
    def run(args: Any, *a: object, **kw: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([str(x) for x in args], rc, out, err)

    monkeypatch.setattr(subprocess, "run", run)


def test_choose_reports_a_simctl_that_cannot_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*a: object, **kw: object) -> None:
        raise FileNotFoundError(2, "No such file or directory")

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(simulator.SimulatorError, match="could not run `xcrun simctl`"):
        simulator.choose("iPhone 16", tmp_path)


def test_choose_reports_a_simctl_that_exits_non_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _simctl_result(monkeypatch, 1, "", "simctl exploded")
    with pytest.raises(simulator.SimulatorError, match="simctl exploded"):
        simulator.choose("iPhone 16", tmp_path)


def test_choose_reports_output_that_is_not_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _simctl_result(monkeypatch, 0, "this is not json")
    with pytest.raises(simulator.SimulatorError):
        simulator.choose("iPhone 16", tmp_path)
    assert not (tmp_path / "simulator.txt").exists()


def test_choose_with_an_empty_setting_and_no_iphones_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake_simctl(monkeypatch, _listing(iOS_18_2=[_dev("PAD", "iPad Pro")]))
    with pytest.raises(
        simulator.SimulatorError, match="no available iPhone simulator was found"
    ):
        simulator.choose("", tmp_path)
