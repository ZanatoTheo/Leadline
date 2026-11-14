"""envload: the app's .env loader (replaces the removed tests/test_env.py)."""

import envload


def use_env_file(monkeypatch, tmp_path, text):
    path = tmp_path / ".env"
    path.write_text(text)
    monkeypatch.setattr(envload, "_find_env_file", lambda: path)


def test_loads_plain_quoted_export_and_comment_lines(monkeypatch, tmp_path):
    for name in ("ENVLOAD_A", "ENVLOAD_B", "ENVLOAD_C", "ENVLOAD_D"):
        monkeypatch.delenv(name, raising=False)
    use_env_file(monkeypatch, tmp_path,
                 "# comment\n\nENVLOAD_A=one\nexport ENVLOAD_B='two words'\nENVLOAD_C=\"three\"\n"
                 "ENVLOAD_D=four # trailing note\nnot a pair\n9BAD=x\n")
    loaded = envload.load_env()
    assert loaded == {"ENVLOAD_A": "one", "ENVLOAD_B": "two words", "ENVLOAD_C": "three", "ENVLOAD_D": "four"}
    import os
    assert os.environ["ENVLOAD_B"] == "two words"
    for name in loaded:
        monkeypatch.delenv(name, raising=False)


def test_shell_values_win_over_the_file(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVLOAD_SHELL", "from-shell")
    use_env_file(monkeypatch, tmp_path, "ENVLOAD_SHELL=from-file\n")
    assert envload.load_env() == {"ENVLOAD_SHELL": "from-shell"}


def test_missing_file_is_fine(monkeypatch):
    monkeypatch.setattr(envload, "_find_env_file", lambda: None)
    assert envload.load_env() == {}
