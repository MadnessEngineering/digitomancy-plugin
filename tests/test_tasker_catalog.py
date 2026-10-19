import pytest

from digitomancy import config, tasker, tasker_catalog as tc

PRJ = """<TaskerData sr="" dvi="1" tv="6.7.6">
<Profile sr="prof1"><edate>{e}</edate><id>1</id><mid0>10</mid0><nme>Front</nme>
  <State sr="con0"><code>165</code><Str sr="arg0">%Door</Str></State></Profile>
<Project sr="proj0"><name>Home</name><pids>1</pids><tids>10,11,12</tids></Project>
<Task sr="task10"><edate>{e}</edate><id>10</id><nme>open front door</nme>
  <Action sr="act0"><code>548</code><Str sr="arg0">opening \x1b[2J</Str></Action></Task>
<Task sr="task11"><edate>{e}</edate><id>11</id><nme>leave home</nme>
  <Action sr="act0"><code>130</code><Str sr="arg0">open front door</Str></Action>
  <Action sr="act1"><code>547</code><label>call mom</label><Str sr="arg0">%n</Str><Str sr="arg1">+1 (555) 123-4567</Str></Action></Task>
<Task sr="task12"><edate>{e}</edate><id>12</id><nme>say hi</nme>
  <Action sr="act0"><code>339</code><Str sr="arg0">Bearer abc123</Str></Action></Task>
</TaskerData>"""


@pytest.fixture
def sources(tmp_path):
    old, new = tmp_path / "old.prj.xml", tmp_path / "backup.xml"
    old.write_text(PRJ.format(e=1000))
    new.write_text(PRJ.format(e=2000).replace("say hi", "say hello"))
    return [old, new]


def test_newest_source_wins_and_hazards_propagate(sources):
    cat = tc.build(sources, manual=["*panic"])
    home = cat["projects"]["Home"]
    assert home["source"].endswith("backup.xml")
    tasks = {t["name"]: t for t in home["tasks"]}
    assert "say hello" in tasks  # from the newer source
    assert tasks["open front door"]["hazard"] and "door" in tasks["open front door"]["hazard_reason"]
    assert tasks["leave home"]["hazard_reason"] == "calls hazard 'open front door'"
    assert not tasks["say hello"]["hazard"]
    assert cat["hazard_tasks"] == ["*panic", "leave home", "open front door"]
    assert cat["callable"] == ["say hello"]
    assert home["profiles"][0]["hazard"] and home["profiles"][0]["contexts"] == ["Variable Value %Door"]


def test_redaction(sources):
    acts = {t["name"]: t["actions"] for t in tc.build(sources)["projects"]["Home"]["tasks"]}
    assert acts["say hello"] == ["HTTP Request [redacted]"]
    assert "555" not in " ".join(acts["leave home"])


def test_bridge_refuses_hazards(sources, workshop, fake):
    config.CATALOG_DIR.mkdir(exist_ok=True)
    tc.write(tc.build(sources), config.CATALOG_DIR)
    (config.CATALOG_DIR / "hazards_manual.txt").write_text("secret thing  # seen live\n")
    d = fake()
    for bad in ("leave home", "secret thing", "open-garage-lot"):  # catalog, manual, name-only
        with pytest.raises(tasker.HazardTask):
            tasker.run_task(d, bad)
    assert tasker.run_task(d, "say hello")["task"] == "say hello"
    assert not any("leave home" in c[1] for c in d.calls if c[0] == "shell")


def test_site_hazard_patterns(sources, workshop, fake, tmp_path):
    pats = tmp_path / "hazard_patterns.txt"
    pats.write_text("# site-specific\nwarehouse\n")
    assert not tc.is_hazard_name("open-warehouse-lot")
    assert tc.is_hazard_name("open-warehouse-lot", pats)
    flagged = tc.build(sources, patterns_file=pats)
    assert flagged["hazard_tasks"] == tc.build(sources)["hazard_tasks"]  # nothing in fixture says warehouse

    config.CATALOG_DIR.mkdir(exist_ok=True)
    (config.CATALOG_DIR / "hazard_patterns.txt").write_text("warehouse\n")
    with pytest.raises(tasker.HazardTask):
        tasker.run_task(fake(), "open-warehouse-lot")
