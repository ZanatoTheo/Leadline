import pytest

from venus.errors import InputError, PluginError
from venus.plugin import Score, load_plugin, load_plugins


def test_toy_plugin_loads(toy_plugin_dir):
    plugin = load_plugin(toy_plugin_dir)
    assert plugin.name == "toy-sentiment"
    assert plugin.version == "1.0.0"
    assert plugin.brief.startswith("Label")
    assert plugin.seed_tendencies[0].id == "t-negation"
    assert plugin.input_schema["required"] == ["text"]


def test_check_returns_score(toy_plugin_dir):
    plugin = load_plugin(toy_plugin_dir)
    score = plugin.check({"text": "x"}, {"label": "negative"}, {"label": "positive"})
    assert isinstance(score, Score)
    assert score.total == 0.0
    assert score.parts == {"label_match": 0.0}
    assert score.reasons == ["expected positive, got negative"]


def test_validate_input_reports_path(toy_plugin_dir):
    plugin = load_plugin(toy_plugin_dir)
    with pytest.raises(InputError) as e:
        plugin.validate_input({"text": 5}, path="cases[0].input")
    assert e.value.code == "input_invalid"
    assert e.value.path == "cases[0].input.text"


def test_missing_manifest(tmp_path):
    with pytest.raises(PluginError) as e:
        load_plugin(tmp_path)
    assert e.value.code == "plugin_manifest_missing"


def test_bad_manifest(plugin_copy):
    with pytest.raises(PluginError) as e:
        load_plugin(plugin_copy(name="Not A Valid Name"))
    assert e.value.code == "plugin_manifest_invalid"
    assert e.value.path == "name"


def test_missing_checker_function(plugin_copy):
    with pytest.raises(PluginError) as e:
        load_plugin(plugin_copy(checker="checker:does_not_exist"))
    assert e.value.code == "plugin_checker_missing"


def test_missing_schema_file(plugin_copy):
    with pytest.raises(PluginError) as e:
        load_plugin(plugin_copy(input_schema="nope.schema.json"))
    assert e.value.code == "plugin_schema_missing"


def test_schema_path_cannot_leave_plugin_folder(plugin_copy):
    with pytest.raises(PluginError) as e:
        load_plugin(plugin_copy(input_schema="../input.schema.json"))
    assert e.value.code == "plugin_manifest_invalid"


def test_score_out_of_range_rejected(plugin_copy):
    plugin = load_plugin(plugin_copy(checker="checker:check_out_of_range"))
    with pytest.raises(PluginError) as e:
        plugin.check({"text": "x"}, {"label": "positive"}, {"label": "positive"})
    assert e.value.code == "plugin_bad_score"


def test_load_plugins_by_name(toy_plugin_dir):
    plugins = load_plugins(toy_plugin_dir.parent)
    assert "toy-sentiment" in plugins
