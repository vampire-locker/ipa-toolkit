import plistlib

from ipa_toolkit.bundle_scan import find_main_app


def _write_info(path: str, *, package_type: str) -> None:
    with open(path, "wb") as f:
        plistlib.dump({"CFBundlePackageType": package_type}, f)


def test_find_main_app_single(tmp_path) -> None:
    payload = tmp_path / "Payload"
    payload.mkdir()
    app = payload / "Only.app"
    app.mkdir()
    _write_info(str(app / "Info.plist"), package_type="APPL")

    picked = find_main_app(str(payload))
    assert picked == str(app)


def test_find_main_app_by_name_without_suffix(tmp_path) -> None:
    payload = tmp_path / "Payload"
    payload.mkdir()
    app_a = payload / "MainA.app"
    app_b = payload / "MainB.app"
    app_a.mkdir()
    app_b.mkdir()
    _write_info(str(app_a / "Info.plist"), package_type="APPL")
    _write_info(str(app_b / "Info.plist"), package_type="APPL")

    picked = find_main_app(str(payload), "MainB")
    assert picked == str(app_b)


def test_find_main_app_by_unique_appl(tmp_path) -> None:
    payload = tmp_path / "Payload"
    payload.mkdir()
    app_a = payload / "Main.app"
    app_b = payload / "Other.app"
    app_a.mkdir()
    app_b.mkdir()
    _write_info(str(app_a / "Info.plist"), package_type="APPL")
    _write_info(str(app_b / "Info.plist"), package_type="FMWK")

    picked = find_main_app(str(payload))
    assert picked == str(app_a)


def test_find_main_app_error_when_ambiguous(tmp_path) -> None:
    payload = tmp_path / "Payload"
    payload.mkdir()
    app_a = payload / "A.app"
    app_b = payload / "B.app"
    app_a.mkdir()
    app_b.mkdir()
    _write_info(str(app_a / "Info.plist"), package_type="APPL")
    _write_info(str(app_b / "Info.plist"), package_type="APPL")

    try:
        find_main_app(str(payload))
        raise AssertionError("expected SystemExit")
    except SystemExit as e:
        msg = str(e)
        assert "multiple .app found" in msg
        assert "--main-app-name" in msg


def test_find_main_app_error_when_named_not_found(tmp_path) -> None:
    payload = tmp_path / "Payload"
    payload.mkdir()
    app = payload / "Only.app"
    app.mkdir()
    _write_info(str(app / "Info.plist"), package_type="APPL")

    try:
        find_main_app(str(payload), "Missing.app")
        raise AssertionError("expected SystemExit")
    except SystemExit as e:
        msg = str(e)
        assert "main app not found" in msg
        assert "Only.app" in msg
