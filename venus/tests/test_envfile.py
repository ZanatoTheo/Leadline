from venus.envfile import load_env


def test_loads_values_and_skips_comments(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# a comment\n\nVERDA_API_KEY=abc123\nexport QUOTED=\"hello world\"\nEMPTY=\n")
    environ = {}
    loaded = load_env(env_file, environ=environ)
    assert environ == {"VERDA_API_KEY": "abc123", "QUOTED": "hello world", "EMPTY": ""}
    assert loaded == environ


def test_shell_value_wins(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("VERDA_API_KEY=from-file\n")
    environ = {"VERDA_API_KEY": "from-shell"}
    loaded = load_env(env_file, environ=environ)
    assert environ["VERDA_API_KEY"] == "from-shell"
    assert loaded == {}


def test_missing_file_is_fine(tmp_path):
    environ = {}
    assert load_env(tmp_path / "nope.env", environ=environ) == {}
    assert environ == {}


def test_finds_env_in_a_parent_folder(tmp_path):
    (tmp_path / ".env").write_text("VERDA_API_KEY=from-parent\n")
    deep = tmp_path / "venus" / "sub"
    deep.mkdir(parents=True)
    environ = {}
    load_env(environ=environ, start=deep)
    assert environ["VERDA_API_KEY"] == "from-parent"


def test_venus_env_file_variable(tmp_path):
    custom = tmp_path / "keys.env"
    custom.write_text("NVIDIA_API_KEY=nv\n")
    environ = {"VENUS_ENV_FILE": str(custom)}
    load_env(environ=environ, start=tmp_path / "elsewhere")
    assert environ["NVIDIA_API_KEY"] == "nv"
