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


LEAKY = """<TaskerData sr="" dvi="1" tv="6.7.6">
<Project sr="proj0"><name>Leaky</name><tids>20,21,22</tids></Project>
<Task sr="task20"><edate>1</edate><id>20</id><nme>wifi share</nme>
  <Action sr="act0"><code>547</code><Str sr="arg0">%WifiPassword</Str><Str sr="arg1">hunter2</Str></Action>
  <Action sr="act1"><code>547</code><Str sr="arg0">%api_key</Str><Str sr="arg1">%input</Str></Action>
  <Action sr="act2"><code>547</code><Str sr="arg0">%token</Str><Str sr="arg1">swordfish!</Str></Action>
  <Action sr="act3"><code>104</code><Str sr="arg0">https://acme.slack.com/archives/D0123456?ts=99</Str></Action>
  <Action sr="act4"><code>339</code><Str sr="arg0">http://192.168.1.50:8080/hook</Str><Str sr="arg1">http://8.8.4.4:9900/x</Str></Action>
  <Action sr="act5"><code>548</code><Str sr="arg0">standup at Acme Corp</Str></Action>
  <Action sr="act6"><code>339</code><Str sr="arg0">Authorization: Basic dXNlcjpodW50ZXIy</Str></Action>
  <Action sr="act7"><code>130</code><Str sr="arg0">a task with a really long name that runs past fifty characters</Str><Str sr="arg1">%pin</Str></Action>
</Task>
<Task sr="task21"><edate>1</edate><id>21</id><nme>a task with a really long name that runs past fifty characters</nme>
  <Action sr="act0"><code>548</code><Str sr="arg0">open the garage</Str></Action></Task>
<Task sr="task22"><edate>1</edate><id>22</id><nme>weather</nme>
  <Action sr="act0"><code>339</code><Str sr="arg0">https://api.example.co.uk/v1?appid=abc</Str></Action>
  <Action sr="act1"><code>339</code><Str sr="arg0">https://api.example.com/v1/chat</Str><Str sr="arg1">Authorization:Bearer %api_key</Str></Action>
  <Action sr="act2"><code>548</code><Str sr="arg0">ssh 8.8.4.4:22 then mqtt 10.0.0.7 v1.2.3</Str></Action></Task>
</TaskerData>"""


@pytest.fixture
def leaky(tmp_path):
    p = tmp_path / "leaky.prj.xml"
    p.write_text(LEAKY)
    site = tmp_path / "redact_patterns.txt"
    site.write_text("# employer\nacme\n")
    cat = tc.build([p], redact_file=site)
    return {t["name"]: t for t in cat["projects"]["Leaky"]["tasks"]}, cat


def test_secret_named_variables_hide_literal_values(leaky):
    tasks, _ = leaky
    acts = tasks["wifi share"]["actions"]
    assert acts[0] == "Variable Set %WifiPassword [redacted]"
    assert acts[1] == "Variable Set %api_key %input"  # variable-to-variable copy stays readable
    assert acts[2] == "Variable Set %token [redacted]"
    blob = " ".join(acts)
    assert "hunter2" not in blob and "swordfish" not in blob and "dXNlcjpodW50ZXIy" not in blob


def test_urls_collapse_to_base_host(leaky):
    tasks, _ = leaky
    acts = tasks["wifi share"]["actions"]
    assert acts[3] == "code:104 [url slack.com]"  # tenant subdomain, path and query gone
    assert acts[4] == "HTTP Request [url lan] [url ip]"
    assert tasks["weather"]["actions"][0] == "HTTP Request [url example.co.uk]"
    assert tc.url_host("https://user:pw@sub.example.com:8443/p") == "example.com"


def test_site_patterns_redact(leaky):
    tasks, _ = leaky
    assert tasks["wifi share"]["actions"][5] == "Flash standup at [redacted] Corp"
    assert "acme" not in " ".join(tasks["wifi share"]["actions"]).lower()
    assert tc._site is None  # build() restores module state


def test_perform_task_target_survives_redaction_and_truncation(leaky):
    tasks, cat = leaky
    long_name = "a task with a really long name that runs past fifty characters"
    assert tasks["wifi share"]["calls"] == [long_name]  # raw name, not the 50-char display
    assert tasks["wifi share"]["actions"][7].startswith("Perform Task a task with")  # target kept, %pin is a var ref
    # the long-named task mentions "garage" -> hazard, and the caller inherits it via the raw call target
    assert {long_name, "wifi share"} <= set(cat["hazard_tasks"])


def test_bare_ips_and_urls_in_sensitive_actions(leaky):
    tasks, _ = leaky
    acts = tasks["weather"]["actions"]
    # %api_key makes the action sensitive; the collapsed URL is still shown, the header isn't
    assert acts[1] == "HTTP Request [url example.com] [redacted]"
    assert acts[2] == "Flash ssh [ip] then mqtt [lan] v1.2.3"
