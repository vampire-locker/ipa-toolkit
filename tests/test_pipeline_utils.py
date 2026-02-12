from pathlib import Path
from types import SimpleNamespace

from ipa_toolkit import pipeline_utils


def test_run_cmd_raises_runtime_error_on_failure(monkeypatch) -> None:
    def fake_run(_cmd, stdout=None, stderr=None, cwd=None, check=False):
        _ = (stdout, stderr, cwd, check)
        return SimpleNamespace(returncode=1, stderr=b"boom")

    monkeypatch.setattr(pipeline_utils.subprocess, "run", fake_run)

    try:
        pipeline_utils.run_cmd(["/usr/bin/false"])
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        msg = str(e)
        assert "Command failed" in msg
        assert "boom" in msg


def test_sign_bundle_recursive_signs_nested_before_main(monkeypatch, tmp_path) -> None:
    app = tmp_path / "Main.app"
    appex = app / "PlugIns" / "Share.appex"
    framework = app / "Frameworks" / "Core.framework"
    dylib = app / "Frameworks" / "libX.dylib"
    xpc = app / "XPCServices" / "Agent.xpc"

    appex.mkdir(parents=True)
    framework.mkdir(parents=True)
    xpc.mkdir(parents=True)
    dylib.write_bytes(b"bin")

    signed: list[tuple[str, str | None]] = []

    monkeypatch.setattr(pipeline_utils.codesign, "remove_signature", lambda _p: None)
    monkeypatch.setattr(
        pipeline_utils.codesign,
        "sign",
        lambda path, identity, entitlements_path=None: signed.append((path, entitlements_path)),
    )
    monkeypatch.setattr(
        pipeline_utils.codesign,
        "write_entitlements",
        lambda _e: str(tmp_path / "ent.plist"),
    )

    ent_map = {
        str(app): {"application-identifier": "TEAM.app"},
        str(appex): {"application-identifier": "TEAM.appex"},
        str(xpc): {"application-identifier": "TEAM.xpc"},
    }

    pipeline_utils.sign_bundle_recursive(
        str(app),
        identity="IDENTITY",
        entitlements_by_bundle=ent_map,
        verbose=False,
    )

    signed_paths = [p for p, _ in signed]
    assert signed_paths[-1] == str(app)
    assert str(appex) in signed_paths
    assert str(framework) in signed_paths
    assert str(dylib) in signed_paths
    assert str(xpc) in signed_paths

    assert signed_paths.index(str(appex)) < signed_paths.index(str(app))
    assert signed_paths.index(str(xpc)) < signed_paths.index(str(app))

    by_path = {p: ent for p, ent in signed}
    assert by_path[str(app)] is not None
    assert by_path[str(appex)] is not None
    assert by_path[str(xpc)] is not None
    assert by_path[str(framework)] is None
    assert by_path[str(dylib)] is None
