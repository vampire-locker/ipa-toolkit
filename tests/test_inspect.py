import plistlib
import zipfile

import pytest

from ipa_toolkit import inspect as inspect_mod
from ipa_toolkit.inspect import inspect_ipa


def _write_inspect_ipa(path, *, multi_top_apps: bool = False) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "Payload/Main.app/Info.plist",
            plistlib.dumps(
                {
                    "CFBundleIdentifier": "com.demo.main",
                    "CFBundlePackageType": "APPL",
                    "CFBundleDisplayName": "Demo",
                    "CFBundleShortVersionString": "1.2.3",
                    "CFBundleVersion": "123",
                    "MinimumOSVersion": "14.0",
                    "CFBundleURLTypes": [
                        {
                            "CFBundleURLSchemes": ["demo", "demo2"],
                        }
                    ],
                }
            ),
        )
        zf.writestr(
            "Payload/Main.app/embedded.mobileprovision",
            b"profile",
        )
        zf.writestr(
            "Payload/Main.app/PlugIns/Share.appex/Info.plist",
            plistlib.dumps(
                {
                    "CFBundleIdentifier": "com.demo.main.share",
                    "CFBundlePackageType": "XPC!",
                }
            ),
        )
        if multi_top_apps:
            zf.writestr(
                "Payload/Other.app/Info.plist",
                plistlib.dumps(
                    {
                        "CFBundleIdentifier": "com.demo.other",
                        "CFBundlePackageType": "APPL",
                    }
                ),
            )


def test_inspect_ipa_reads_main_and_nested_info(monkeypatch, tmp_path) -> None:
    ipa_path = tmp_path / "inspect.ipa"
    _write_inspect_ipa(ipa_path)

    monkeypatch.setattr(
        inspect_mod,
        "_inspect_signature_info",
        lambda _p, main_app_name="": (
            True,
            "com.demo.main",
            "TEAM123",
            ["Apple Distribution: Example Co. (TEAM123)"],
            "",
        ),
    )

    info = inspect_ipa(str(ipa_path))
    assert info.main_app.name == "Main.app"
    assert info.main_app.bundle_id == "com.demo.main"
    assert info.display_name == "Demo"
    assert info.version == "1.2.3"
    assert info.build == "123"
    assert info.min_os_version == "14.0"
    assert info.has_embedded_profile is True
    assert info.is_signed is True
    assert info.signature_identifier == "com.demo.main"
    assert info.signature_team_id == "TEAM123"
    assert info.signature_authorities == ["Apple Distribution: Example Co. (TEAM123)"]
    assert info.signature_error == ""
    assert info.url_schemes == ["demo", "demo2"]
    assert len(info.nested_bundles) == 1
    assert info.nested_bundles[0].name == "Share.appex"
    assert info.nested_bundles[0].bundle_id == "com.demo.main.share"


def test_inspect_ipa_requires_main_app_name_when_ambiguous(monkeypatch, tmp_path) -> None:
    ipa_path = tmp_path / "inspect.ipa"
    _write_inspect_ipa(ipa_path, multi_top_apps=True)

    monkeypatch.setattr(
        inspect_mod,
        "_inspect_signature_info",
        lambda _p, main_app_name="": (
            False,
            "",
            "",
            [],
            "code object is not signed at all",
        ),
    )

    with pytest.raises(SystemExit) as e:
        inspect_ipa(str(ipa_path))
    assert "multiple .app found" in str(e.value)
    assert "--main-app-name" in str(e.value)

    info = inspect_ipa(str(ipa_path), main_app_name="Main")
    assert info.main_app.name == "Main.app"
