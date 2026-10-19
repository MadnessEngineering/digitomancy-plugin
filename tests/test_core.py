import pytest
from pathlib import Path

from digitomancy import checkpoints, config, maps, routines, tasker, ui
from digitomancy.device import keycode, parse_component, parse_resumed, to_pixels

XML = """<hierarchy rotation="0">
<node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.x" content-desc="" clickable="false" bounds="[0,0][1000,2000]">
  <node index="0" text="Wi-Fi" resource-id="com.x:id/title" class="android.widget.TextView" package="com.x" content-desc="" clickable="true" bounds="[0,100][1000,300]" />
  <node index="1" text="" resource-id="" class="android.view.View" package="com.x" content-desc="" clickable="false" bounds="[0,300][1000,400]" />
  <node index="2" text="" resource-id="" class="android.widget.ImageButton" package="com.x" content-desc="Back" clickable="true" bounds="[0,0][100,100]" />
</node></hierarchy>"""


def test_to_pixels_normalized_vs_absolute():
    assert to_pixels(0.5, 0.25, (1000, 2000)) == (500, 500)
    assert to_pixels(500, 500, (1000, 2000)) == (500, 500)
    assert to_pixels(1, 1, (1000, 2000)) == (1, 1)  # ints are pixels even when ≤1


def test_ui_parse_keeps_interesting_nodes():
    nodes = ui.parse(XML)
    assert [n.text or n.desc for n in nodes] == ["Wi-Fi", "Back"]
    assert nodes[0].center == (0.5, 0.1)
    assert nodes[0].selector() == {"resourceId": "com.x:id/title", "text": "Wi-Fi"}
    assert nodes[1].selector() == {"description": "Back"}
    assert "#0 TextView 'Wi-Fi' id=title @(0.500,0.100) tap" in ui.render(nodes)


def test_save_and_tap_anchor_selector_then_point(workshop, fake):
    maps.save_anchor("app", "ok", selector={"text": "OK"}, point=(0.5, 0.9), app="com.x")
    m = maps.load_map("app")
    assert m.app == "com.x" and m.anchors["ok"].point == (0.5, 0.9)

    present = fake(present=[{"text": "OK"}])
    assert maps.tap_anchor(present, "app:ok") == "selector"
    absent = fake()
    assert maps.tap_anchor(absent, "app:ok") == "point"
    assert absent.calls == [("tap", 0.5, 0.9)]

    maps.save_anchor("app", "bare", selector={"text": "nope"})
    with pytest.raises(maps.AnchorMissed):
        maps.tap_anchor(absent, "app:bare")


def test_checkpoint_all_any_and_failure_snapshot(workshop, fake):
    d = fake(present=[{"text": "A"}])
    assert checkpoints.evaluate(d, [{"app": "com.android.settings"}, {"selector": {"text": "A"}}]).ok
    assert not checkpoints.evaluate(d, [{"selector": {"text": "B"}}]).ok
    assert checkpoints.evaluate(d, {"any": [{"selector": {"text": "B"}}, {"gone": {"text": "B"}}]}).ok
    with pytest.raises(checkpoints.CheckpointFailed) as e:
        checkpoints.expect(d, [{"app": "com.other"}], timeout=0)
    assert e.value.snapshot.exists()


def test_routine_stages_fail_and_resume(workshop, fake):
    (config.MAPS_DIR / "m.yaml").write_text(
        "anchors: {go: {selector: {text: Go}}}\n"
        "screens: {start: [{selector: {text: Go}}], done: [{selector: {text: Done}}]}\n"
    )
    r = routines.Routine("t.flow")

    @r.stage("open")
    def _(ctx):
        ctx.expect("m:start", timeout=0)

    @r.stage("go", requires="m:start")
    def _(ctx):
        ctx.tap("m:go")
        ctx.expect("m:done", timeout=0)

    d = fake(present=[{"text": "Go"}])
    rep = routines.run("t.flow", d)
    assert not rep["ok"] and rep["passed"] == ["open"] and rep["failed"]["stage"] == "go"

    d.present.append({"text": "Done"})
    rep = routines.run("t.flow", d, resume_from="go")
    assert rep["ok"] and rep["passed"] == ["go"]


def test_single_stage_routine_gets_params(workshop, fake):
    @routines.routine("t.keys")
    def _(ctx, times="1"):
        for _ in range(int(times)):
            ctx.key("back")

    d = fake()
    assert routines.run("t.keys", d, {"times": "3"})["ok"]
    assert d.calls == [("key", "back")] * 3


def test_tasker_broadcast_quoting():
    cmd = tasker.broadcast_cmd("Say Hi", {"par1": "it's me"}, "abc")
    assert cmd.startswith("am broadcast -a cc.madness.digitomancy.RUN --es task 'Say Hi'")
    assert "--es par1 'it'\"'\"'s me'" in cmd and cmd.endswith("--es dgm_id abc")


def test_unknown_device_name_is_raw_serial(workshop):
    (workshop / "devices.yaml").write_text("default: a\ndevices: {a: {serial: X1}}\n")
    assert config.resolve_device().serial == "X1"
    assert config.resolve_device("10.0.0.5:5555").connect


def test_parse_resumed_from_dumpsys():
    out = "    topResumedActivity=ActivityRecord{162340298 u0 com.android.settings/.Settings t43395}"
    assert parse_resumed(out) == {"package": "com.android.settings", "activity": "com.android.settings.Settings"}
    assert parse_resumed("nothing here") is None


def test_parse_resumed_ignores_scrcpy_virtual_display():
    out = (
        "Display #20 (activities from top to bottom):\n"
        "    topResumedActivity=ActivityRecord{1 u0 com.savetheworld.game/com.google.firebase.MessagingUnityPlayerActivity t9}\n"
        "Display #0 (activities from top to bottom):\n"
        "    topResumedActivity=ActivityRecord{2 u0 com.android.settings/.Settings$DevelopmentSettingsActivity t8}\n"
    )
    assert parse_resumed(out)["activity"] == "com.android.settings.Settings$DevelopmentSettingsActivity"
    assert parse_resumed(out, display=20)["package"] == "com.savetheworld.game"


def test_keycode_names():
    assert keycode("back") == "KEYCODE_BACK"
    assert keycode("recent") == "KEYCODE_APP_SWITCH"
    assert keycode("volume_up") == "KEYCODE_VOLUME_UP"
    assert keycode("KEYCODE_ENTER") == "KEYCODE_ENTER" and keycode("4") == "4"


def test_parse_component_from_resolve_activity():
    out = "priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=true\nnet.dinglisch.android.taskerm/.Tasker\n"
    assert parse_component(out) == "net.dinglisch.android.taskerm/.Tasker"
    assert parse_component("No activity found") is None


def test_default_home_order(tmp_path, monkeypatch):
    monkeypatch.setenv("DGM_HOME", str(tmp_path / "x"))
    assert config._default_home() == tmp_path / "x"
    monkeypatch.delenv("DGM_HOME")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    assert config._default_home(checkout) == Path.home() / ".digitomancy"  # installed copy
    (checkout / "devices.yaml").write_text("devices: {}\n")
    assert config._default_home(checkout) == checkout  # source checkout is its own workspace


def test_ensure_workspace_seeds_without_clobbering(workshop):
    (config.MAPS_DIR / "settings.yaml").write_text("app: mine\n")
    created = config.ensure_workspace()
    names = {p.rsplit("/", 1)[-1] for p in created}
    assert {"devices.yaml", "devopts.yaml", "tasker.yaml", "devopts.py", "tasker_app.py"} <= names
    assert "settings.yaml" not in names
    assert (config.MAPS_DIR / "settings.yaml").read_text() == "app: mine\n"
    assert "CHANGE_ME" in config.DEVICES_FILE.read_text()
    assert config.ensure_workspace() == []  # idempotent


def test_starters_load(workshop):
    config.ensure_workspace()
    for name in maps.list_maps():
        maps.load_map(name)
    routines.REGISTRY.clear()
    assert {"settings.wifi", "devopts.scan", "tasker.profiles"} <= set(routines.load_all())
