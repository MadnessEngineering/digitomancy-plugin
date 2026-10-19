"""Thin wrapper over uiautomator2 with normalized coordinates.

Coordinate rule (used everywhere): floats in [0, 1] are fractions of the
screen; anything else is absolute pixels. Maps store fractions so one anchor
works across the phone and BlueStacks at different resolutions.
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from .config import DeviceSpec, resolve_device


def is_normalized(x: float, y: float) -> bool:
    return isinstance(x, float) and isinstance(y, float) and 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0


def to_pixels(x: float, y: float, size: tuple[int, int]) -> tuple[int, int]:
    if is_normalized(x, y):
        return round(x * size[0]), round(y * size[1])
    return int(x), int(y)


_DISPLAY = re.compile(r"^Display #(\d+)", re.M)
_RESUMED = re.compile(r"(?:topResumedActivity=|ResumedActivity: |Resumed: )ActivityRecord\{\S+ u\d+ ([\w.]+)/([\w.$]+)")


def parse_resumed(dumpsys: str, display: int = 0) -> dict | None:
    """Foreground app on one display from `dumpsys activity activities`.

    Must be per-display: scrcpy `--new-display` (and Android desktop mode) host
    apps on virtual displays, and each display has its own resumed activity.
    A global first-match returned a game on scrcpy display #20 while Settings
    was on the physical screen. uiautomator2's app_current() fell for the same.
    """
    heads = list(_DISPLAY.finditer(dumpsys))
    section = dumpsys
    for i, h in enumerate(heads):
        if int(h.group(1)) == display:
            section = dumpsys[h.end() : heads[i + 1].start() if i + 1 < len(heads) else len(dumpsys)]
            break
    m = _RESUMED.search(section)
    if not m:
        return None
    pkg, act = m.groups()
    return {"package": pkg, "activity": pkg + act if act.startswith(".") else act}


_KEY_ALIASES = {"recent": "APP_SWITCH", "recents": "APP_SWITCH", "delete": "DEL", "backspace": "DEL"}


def keycode(name: str) -> str:
    if name.upper().startswith("KEYCODE_") or name.isdigit():
        return name.upper()
    return "KEYCODE_" + _KEY_ALIASES.get(name.lower(), name.upper())


def parse_component(resolve_out: str) -> str | None:
    """Last `pkg/activity` line of `cmd package resolve-activity --brief`."""
    lines = [ln.strip() for ln in resolve_out.splitlines() if "/" in ln and "=" not in ln]
    return lines[-1] if lines else None


def adb(serial: str, *args: str, timeout: float = 20) -> str:
    out = subprocess.run(["adb", "-s", serial, *args], capture_output=True, text=True, timeout=timeout)
    if out.returncode != 0:
        raise RuntimeError(f"adb {' '.join(args)} failed: {out.stderr.strip() or out.stdout.strip()}")
    return out.stdout


class Device:
    def __init__(self, spec: DeviceSpec):
        self.spec = spec
        self._u2 = None
        self.last_used = 0.0  # monotonic; the MCP idle watchdog reads it

    @classmethod
    def named(cls, name: str | None = None) -> "Device":
        return cls(resolve_device(name))

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def serial(self) -> str:
        return self.spec.serial

    @property
    def u2(self):
        self.last_used = time.monotonic()
        if self._u2 is None:
            import uiautomator2  # heavy import; keep CLI --help fast

            if self.spec.connect:
                subprocess.run(["adb", "connect", self.serial], capture_output=True, timeout=10)
            self._u2 = uiautomator2.connect(self.serial)
        return self._u2

    @property
    def connected(self) -> bool:
        return self._u2 is not None

    def release(self) -> bool:
        """Stop the on-device uiautomator server.

        While it runs, Android SUPPRESSES every accessibility service — on a
        Pixel 9 test phone: Tasker, AutoInput, Join, Button Mapper all unbound
        (`dumpsys accessibility` Bound services:{}), and they rebind once it
        stops. The server outlives our process, so always release when done.
        """
        if self._u2 is None:
            return False
        try:
            self._u2.stop_uiautomator()
        finally:
            self._u2 = None
        return True

    def _read(self, fn):
        """One retry for READ-ONLY u2 calls. The on-device u2 server sometimes
        drops a request ("Remote end closed connection without response") —
        seen twice on the Pixel 9. Never wrap taps: a retry could act twice."""
        try:
            return fn()
        except Exception as e:
            if "Remote end closed" not in str(e) and "Connection aborted" not in str(e):
                raise
            time.sleep(1.0)
            return fn()

    # --- state -----------------------------------------------------------
    @property
    def size(self) -> tuple[int, int]:
        return tuple(self._read(self.u2.window_size))

    def current_app(self) -> dict:
        # No u2.app_current() fallback: it reported apps from the scrcpy virtual
        # display twice. Unknown beats confidently wrong; checkpoints just retry.
        out = self.shell("dumpsys activity activities | grep -E '^Display #|Resumed'; true")
        return parse_resumed(out) or {"package": None, "activity": None}

    def dump(self) -> str:
        return self._read(lambda: self.u2.dump_hierarchy(compressed=False))

    def screenshot(self, path: Path | None = None):
        img = self._read(self.u2.screenshot)  # PIL.Image
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path)
        return img

    # --- input -----------------------------------------------------------
    def tap(self, x: float, y: float) -> tuple[int, int]:
        px = to_pixels(x, y, self.size)
        self.u2.click(*px)
        return px

    def long_press(self, x: float, y: float, duration: float = 0.8) -> tuple[int, int]:
        px = to_pixels(x, y, self.size)
        self.u2.long_click(*px, duration)
        return px

    def swipe(self, x1: float, y1: float, x2: float, y2: float, duration: float = 0.3) -> None:
        size = self.size
        self.u2.swipe(*to_pixels(x1, y1, size), *to_pixels(x2, y2, size), duration=duration)

    def key(self, key: str) -> None:
        """home/back/enter/recent/power/volume_up… or a raw KEYCODE_* name.

        Sent via `input keyevent`, not u2.press(): on the Pixel a u2 Back
        didn't close a Tasker scene that a raw keyevent closed at once.
        """
        self.shell(f"input keyevent {keycode(key)}")

    def type_text(self, text: str, clear: bool = False) -> None:
        self.u2.send_keys(text, clear=clear)

    def launch(self, package: str, stop_first: bool = False, activity: str | None = None) -> str:
        """Start the app's DEFAULT launcher activity on the physical display.

        Not u2.app_start(): with no activity it uses `monkey -c LAUNCHER`, which
        picks randomly among launcher activities. Tasker has two — the second
        (ActivitySecondaryApp) runs a task, which is how a launch kept opening
        a user's Tasker scene. Resolve the default like a launcher would.
        """
        if stop_first:
            self.shell(f"am force-stop {package}")
        comp = activity or self.resolve_launcher(package)
        self.shell(f"am start --display 0 -n {comp}")
        return comp

    def resolve_launcher(self, package: str) -> str:
        out = self.shell(f"cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.LAUNCHER {package}")
        comp = parse_component(out)
        if not comp:
            raise RuntimeError(f"no launcher activity for {package}: {out.strip()!r}")
        return comp

    def stop(self, package: str) -> None:
        self.u2.app_stop(package)

    def shell(self, cmd: str, timeout: float = 20) -> str:
        return adb(self.serial, "shell", cmd, timeout=timeout)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    # --- selectors (thin, so tests can fake them) -------------------------
    def exists(self, selector: dict) -> bool:
        return bool(self._read(lambda: self.u2(**selector).exists))

    def wait_exists(self, selector: dict, timeout: float) -> bool:
        return bool(self._read(lambda: self.u2(**selector).wait(timeout=timeout)))

    def click_selector(self, selector: dict) -> None:
        self.u2(**selector).click()
