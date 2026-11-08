"""`bull doctor`: the install and toolchain check."""

from __future__ import annotations

from bull.Modules.appinit.Contracts import Doctor, DoctorReport


class LiveDoctor(Doctor):
    def run(self) -> DoctorReport:
        raise NotImplementedError(f"{type(self).__name__}.run")
