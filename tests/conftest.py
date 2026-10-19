import pytest

from digitomancy import config


class FakeDevice:
    """Enough of Device for maps/checkpoints/routines without a phone."""

    name = "fake"

    def __init__(self, present=(), app="com.android.settings", activity=".Settings"):
        self.present = list(present)  # selectors that "exist"
        self.app = {"package": app, "activity": activity}
        self.calls = []
        self.size = (1000, 2000)

    def exists(self, selector):
        return selector in self.present

    def wait_exists(self, selector, timeout):
        return self.exists(selector)

    def click_selector(self, selector):
        self.calls.append(("click", selector))

    def tap(self, x, y):
        self.calls.append(("tap", x, y))
        return (x, y)

    def current_app(self):
        return self.app

    def launch(self, pkg, stop_first=False):
        self.calls.append(("launch", pkg))

    def key(self, k):
        self.calls.append(("key", k))

    def shell(self, cmd, timeout=20):
        self.calls.append(("shell", cmd))
        return "Broadcast completed: result=0"

    def screenshot(self, path=None):
        if path:
            path.write_bytes(b"")

    def dump(self):
        return "<hierarchy/>"

    def sleep(self, s):
        pass


@pytest.fixture
def workshop(tmp_path, monkeypatch):
    """Point config at a temp workshop so tests never touch the real maps."""
    for attr, sub in (("MAPS_DIR", "maps"), ("ROUTINES_DIR", "routines"), ("RUNS_DIR", ".runs"), ("CATALOG_DIR", "catalog")):
        (tmp_path / sub).mkdir()
        monkeypatch.setattr(config, attr, tmp_path / sub)
    monkeypatch.setattr(config, "DEVICES_FILE", tmp_path / "devices.yaml")
    return tmp_path


@pytest.fixture
def fake():
    return FakeDevice
