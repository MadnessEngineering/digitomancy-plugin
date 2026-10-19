"""Example routines — copy this file to start a new one."""

from digitomancy.routines import Routine, routine

wifi = Routine("settings.wifi", "Open Settings and land on the Wi-Fi/Internet page")


@wifi.stage("open")
def _(ctx):
    ctx.launch("com.android.settings", stop_first=True)
    ctx.expect("settings:home")


@wifi.stage("network", requires="settings:home")
def _(ctx):
    ctx.tap("settings:network")
    ctx.expect("settings:network")


@wifi.stage("wifi", requires="settings:network")
def _(ctx):
    ctx.tap("settings:wifi")


@routine("phone.home_and_back", "Home, then back — smoke test that input works", params={"times": "how many back presses"})
def home_and_back(ctx, times="1"):
    ctx.key("home")
    for _ in range(int(times)):
        ctx.key("back")
