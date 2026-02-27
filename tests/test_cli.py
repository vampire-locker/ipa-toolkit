from pathlib import Path

import pytest

from ipa_toolkit import cli
from ipa_toolkit.provisioning import ProvisioningProfile


def _write_dummy_ipa(path: Path) -> None:
    path.write_bytes(b"not-a-real-ipa")


class _FakeStdin:
    def __init__(self, *, is_tty: bool) -> None:
        self._is_tty = is_tty

    def isatty(self) -> bool:
        return self._is_tty


def test_main_auto_detects_single_profile_when_p_omitted(monkeypatch, tmp_path) -> None:
    ipa_path = tmp_path / "app.ipa"
    profile = tmp_path / "only.mobileprovision"
    output = tmp_path / "out.ipa"
    _write_dummy_ipa(ipa_path)
    profile.write_bytes(b"profile")

    captured: dict = {}

    def fake_resign_ipa(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(cli, "resign_ipa", fake_resign_ipa)

    rc = cli.main(["-i", str(ipa_path), "-o", str(output), "-s", "IDENTITY"])
    assert rc == 0
    assert captured["profile_path"] == str(profile)


def test_main_selects_profile_when_multiple_auto_profiles(monkeypatch, tmp_path) -> None:
    ipa_path = tmp_path / "app.ipa"
    _write_dummy_ipa(ipa_path)
    profile_a = tmp_path / "a.mobileprovision"
    profile_b = tmp_path / "b.mobileprovision"
    profile_a.write_bytes(b"a")
    profile_b.write_bytes(b"b")

    captured: dict = {}
    monkeypatch.setattr(cli, "resign_ipa", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(cli.sys, "stdin", _FakeStdin(is_tty=True))
    monkeypatch.setattr("builtins.input", lambda _prompt: "2")

    rc = cli.main(["-i", str(ipa_path), "-s", "IDENTITY"])
    assert rc == 0
    assert captured["profile_path"] == str(profile_b)


def test_main_errors_when_multiple_auto_profiles_non_interactive(monkeypatch, tmp_path) -> None:
    ipa_path = tmp_path / "app.ipa"
    _write_dummy_ipa(ipa_path)
    (tmp_path / "a.mobileprovision").write_bytes(b"a")
    (tmp_path / "b.mobileprovision").write_bytes(b"b")

    monkeypatch.setattr(cli, "resign_ipa", lambda **_kwargs: None)
    monkeypatch.setattr(cli.sys, "stdin", _FakeStdin(is_tty=False))

    with pytest.raises(SystemExit) as e:
        cli.main(["-i", str(ipa_path), "-s", "IDENTITY"])
    assert "multiple provisioning profiles found" in str(e.value)
    assert "non-interactive mode" in str(e.value)


def test_main_infers_sign_identity_from_profile(monkeypatch, tmp_path) -> None:
    ipa_path = tmp_path / "app.ipa"
    profile = tmp_path / "app.mobileprovision"
    _write_dummy_ipa(ipa_path)
    profile.write_bytes(b"profile")

    captured: dict = {}

    monkeypatch.setattr(cli, "resign_ipa", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(
        cli,
        "load_mobileprovision",
        lambda _path: ProvisioningProfile(raw={}, team_id="TEAM123", entitlements={}),
    )
    monkeypatch.setattr(
        cli,
        "resolve_sign_identity_from_profile",
        lambda _profile: "Apple Distribution: Example (TEAM123)",
    )

    rc = cli.main(["-i", str(ipa_path), "-p", str(profile)])
    assert rc == 0
    assert captured["sign_identity"] == "Apple Distribution: Example (TEAM123)"


def test_main_requires_s_or_profile_for_auto_identity(monkeypatch, tmp_path) -> None:
    ipa_path = tmp_path / "app.ipa"
    _write_dummy_ipa(ipa_path)

    monkeypatch.setattr(cli, "resign_ipa", lambda **_kwargs: None)

    with pytest.raises(SystemExit) as e:
        cli.main(["-i", str(ipa_path)])
    assert "missing -s/--sign-identity" in str(e.value)


def test_main_auto_detects_single_input_ipa_when_i_omitted(monkeypatch, tmp_path) -> None:
    ipa_path = tmp_path / "auto.ipa"
    _write_dummy_ipa(ipa_path)
    monkeypatch.chdir(tmp_path)

    captured: dict = {}
    monkeypatch.setattr(cli, "resign_ipa", lambda **kwargs: captured.update(kwargs))

    rc = cli.main(["-s", "IDENTITY"])
    assert rc == 0
    assert captured["input_ipa"] == str(ipa_path)
    assert captured["output_ipa"] == str(tmp_path / "auto.resigned.ipa")


def test_main_interactively_selects_input_ipa_when_multiple_in_cwd(monkeypatch, tmp_path) -> None:
    ipa_a = tmp_path / "a.ipa"
    ipa_b = tmp_path / "b.ipa"
    _write_dummy_ipa(ipa_a)
    _write_dummy_ipa(ipa_b)
    monkeypatch.chdir(tmp_path)
    captured: dict = {}
    monkeypatch.setattr(cli, "resign_ipa", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(cli.sys, "stdin", _FakeStdin(is_tty=True))
    monkeypatch.setattr("builtins.input", lambda _prompt: "1")

    rc = cli.main(["-s", "IDENTITY"])
    assert rc == 0
    assert captured["input_ipa"] == str(ipa_a)
    assert captured["output_ipa"] == str(tmp_path / "a.resigned.ipa")


def test_main_errors_when_multiple_input_ipas_in_cwd_non_interactive(monkeypatch, tmp_path) -> None:
    _write_dummy_ipa(tmp_path / "a.ipa")
    _write_dummy_ipa(tmp_path / "b.ipa")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "resign_ipa", lambda **_kwargs: None)
    monkeypatch.setattr(cli.sys, "stdin", _FakeStdin(is_tty=False))

    with pytest.raises(SystemExit) as e:
        cli.main(["-s", "IDENTITY"])
    assert "multiple .ipa files found" in str(e.value)
    assert "non-interactive mode" in str(e.value)


def test_main_errors_when_no_input_ipa_in_cwd(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "resign_ipa", lambda **_kwargs: None)

    with pytest.raises(SystemExit) as e:
        cli.main(["-s", "IDENTITY"])
    assert "no .ipa file found in current directory" in str(e.value)


def test_main_passes_auto_rewrite_bundle_id_values_flag(monkeypatch, tmp_path) -> None:
    ipa_path = tmp_path / "app.ipa"
    _write_dummy_ipa(ipa_path)
    captured: dict = {}
    monkeypatch.setattr(cli, "resign_ipa", lambda **kwargs: captured.update(kwargs))

    rc = cli.main(
        [
            "-i",
            str(ipa_path),
            "-s",
            "IDENTITY",
            "--auto-rewrite-bundle-id-values",
        ]
    )
    assert rc == 0
    assert captured["auto_rewrite_bundle_id_values"] is True


def test_main_inspect_mode_skips_resign_and_sign_identity(monkeypatch, tmp_path) -> None:
    ipa_path = tmp_path / "app.ipa"
    _write_dummy_ipa(ipa_path)

    called: dict = {"inspect": False, "print": False, "resign": False}

    def fake_inspect(input_ipa: str, main_app_name: str = "") -> dict:
        called["inspect"] = True
        return {"input_ipa": input_ipa, "main_app_name": main_app_name}

    monkeypatch.setattr(
        cli,
        "inspect_ipa",
        fake_inspect,
    )
    monkeypatch.setattr(
        cli,
        "print_ipa_info",
        lambda _info: called.__setitem__("print", True),
    )
    monkeypatch.setattr(
        cli,
        "resign_ipa",
        lambda **_kwargs: called.__setitem__("resign", True),
    )

    rc = cli.main(["-i", str(ipa_path), "--inspect"])
    assert rc == 0
    assert called["inspect"] is True
    assert called["print"] is True
    assert called["resign"] is False


def test_main_passes_dry_run_flag(monkeypatch, tmp_path) -> None:
    ipa_path = tmp_path / "app.ipa"
    _write_dummy_ipa(ipa_path)
    captured: dict = {}
    monkeypatch.setattr(cli, "resign_ipa", lambda **kwargs: captured.update(kwargs))

    rc = cli.main(["-i", str(ipa_path), "-s", "IDENTITY", "--dry-run"])
    assert rc == 0
    assert captured["dry_run"] is True


def test_main_rejects_dry_run_with_inspect(tmp_path) -> None:
    ipa_path = tmp_path / "app.ipa"
    _write_dummy_ipa(ipa_path)

    with pytest.raises(SystemExit) as e:
        cli.main(["-i", str(ipa_path), "--inspect", "--dry-run"])
    assert "--inspect and --dry-run cannot be used together" in str(e.value)
