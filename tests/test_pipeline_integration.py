import plistlib
import zipfile
from pathlib import Path

from ipa_toolkit import ipa as ipa_mod
from ipa_toolkit.provisioning import ProvisioningProfile
from ipa_toolkit.types import Op


def _create_minimal_ipa(ipa_path: Path) -> None:
    with zipfile.ZipFile(ipa_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "Payload/Main.app/Info.plist",
            plistlib.dumps(
                {
                    "CFBundleIdentifier": "com.old.app",
                    "CFBundlePackageType": "APPL",
                    "CFBundleShortVersionString": "1.0",
                    "CFBundleVersion": "1",
                    "CFBundleURLTypes": [
                        {
                            "CFBundleURLName": "com.old.app",
                            "CFBundleURLSchemes": ["com.old.app", "myapp"],
                        }
                    ],
                }
            ),
        )
        zf.writestr(
            "Payload/Main.app/PlugIns/Share.appex/Info.plist",
            plistlib.dumps(
                {
                    "CFBundleIdentifier": "com.old.app.share",
                    "CFBundlePackageType": "XPC!",
                    "CFBundleURLTypes": [
                        {
                            "CFBundleURLSchemes": ["com.old.app.share", "sharetool"],
                        }
                    ],
                }
            ),
        )
        zf.writestr("Symbols/dummy.txt", b"symbol")


def test_resign_pipeline_updates_ids_and_keeps_top_level_items(monkeypatch, tmp_path) -> None:
    input_ipa = tmp_path / "input.ipa"
    output_ipa = tmp_path / "output.ipa"
    _create_minimal_ipa(input_ipa)

    signed: list[tuple[str, str | None]] = []
    verified: list[str] = []

    def fake_sign(path: str, identity: str, entitlements_path: str | None = None) -> None:
        _ = identity
        signed.append((path, entitlements_path))

    def fake_verify(path: str) -> None:
        verified.append(path)

    monkeypatch.setattr(ipa_mod.codesign, "remove_signature", lambda _p: None)
    monkeypatch.setattr(ipa_mod.codesign, "sign", fake_sign)
    monkeypatch.setattr(ipa_mod.codesign, "verify", fake_verify)
    monkeypatch.setattr(ipa_mod.codesign, "extract_entitlements", lambda _p: None)
    monkeypatch.setattr(
        ipa_mod.codesign,
        "write_entitlements",
        lambda ent: str(tmp_path / f"ents_{len(ent)}.plist"),
    )

    ipa_mod.resign_ipa(
        input_ipa=str(input_ipa),
        output_ipa=str(output_ipa),
        sign_identity="IDENTITY",
        profile_path="",
        entitlements_path="",
        main_app_name="",
        strict_entitlements=False,
        keep_temp=False,
        verbose=False,
        new_bundle_id="com.new.app",
        new_version="2.0",
        new_build="200",
        new_display_name="NewName",
        ops=[Op(scope="all", kind="set_string", key_path="A:B", value="v")],
    )

    assert output_ipa.exists()

    with zipfile.ZipFile(output_ipa, "r") as zf:
        names = set(zf.namelist())
        assert "Payload/Main.app/Info.plist" in names
        assert "Payload/Main.app/PlugIns/Share.appex/Info.plist" in names
        assert "Symbols/dummy.txt" in names

        main_plist = plistlib.loads(zf.read("Payload/Main.app/Info.plist"))
        ext_plist = plistlib.loads(zf.read("Payload/Main.app/PlugIns/Share.appex/Info.plist"))

    assert main_plist["CFBundleIdentifier"] == "com.new.app"
    assert ext_plist["CFBundleIdentifier"] == "com.new.app.share"
    assert main_plist["CFBundleShortVersionString"] == "2.0"
    assert main_plist["CFBundleVersion"] == "200"
    assert main_plist["CFBundleDisplayName"] == "NewName"
    assert main_plist["CFBundleName"] == "NewName"
    assert main_plist["A"]["B"] == "v"
    assert main_plist["CFBundleURLTypes"][0]["CFBundleURLName"] == "com.new.app"
    assert main_plist["CFBundleURLTypes"][0]["CFBundleURLSchemes"][0] == "com.new.app"
    assert ext_plist["CFBundleURLTypes"][0]["CFBundleURLSchemes"][0] == "com.new.app.share"

    assert verified
    assert any(path.endswith("Main.app") for path, _ in signed)
    assert any(path.endswith("Share.appex") for path, _ in signed)


def test_resign_pipeline_embeds_profile_when_provided(monkeypatch, tmp_path) -> None:
    input_ipa = tmp_path / "input.ipa"
    output_ipa = tmp_path / "output.ipa"
    profile = tmp_path / "test.mobileprovision"
    profile.write_bytes(b"profile-data")
    _create_minimal_ipa(input_ipa)

    monkeypatch.setattr(ipa_mod.codesign, "remove_signature", lambda _p: None)
    monkeypatch.setattr(ipa_mod.codesign, "sign", lambda _p, _i, entitlements_path=None: None)
    monkeypatch.setattr(ipa_mod.codesign, "verify", lambda _p: None)
    monkeypatch.setattr(ipa_mod.codesign, "extract_entitlements", lambda _p: None)
    monkeypatch.setattr(
        ipa_mod.codesign,
        "write_entitlements",
        lambda _e: str(tmp_path / "ents.plist"),
    )
    monkeypatch.setattr(
        ipa_mod,
        "load_mobileprovision",
        lambda _p: ProvisioningProfile(raw={}, team_id="TEAM123", entitlements={}),
    )

    ipa_mod.resign_ipa(
        input_ipa=str(input_ipa),
        output_ipa=str(output_ipa),
        sign_identity="IDENTITY",
        profile_path=str(profile),
        entitlements_path="",
        main_app_name="Main.app",
        strict_entitlements=False,
        keep_temp=False,
        verbose=False,
        new_bundle_id="",
        new_version="",
        new_build="",
        new_display_name="",
        ops=[],
    )

    with zipfile.ZipFile(output_ipa, "r") as zf:
        assert "Payload/Main.app/embedded.mobileprovision" in zf.namelist()
        assert zf.read("Payload/Main.app/embedded.mobileprovision") == b"profile-data"


def test_resign_pipeline_auto_rewrites_bundle_id_like_plist_values(monkeypatch, tmp_path) -> None:
    input_ipa = tmp_path / "input.ipa"
    output_ipa = tmp_path / "output.ipa"
    with zipfile.ZipFile(input_ipa, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "Payload/Main.app/Info.plist",
            plistlib.dumps(
                {
                    "CFBundleIdentifier": "com.old.app",
                    "CFBundlePackageType": "APPL",
                    "WKCompanionAppBundleIdentifier": "com.old.app.watch",
                    "AlreadyNew": "com.new.app.watch",
                    "Mixed": ["com.old.app", "prefix.com.old.app", {"Deep": "com.old.app.ext"}],
                }
            ),
        )

    monkeypatch.setattr(ipa_mod.codesign, "remove_signature", lambda _p: None)
    monkeypatch.setattr(ipa_mod.codesign, "sign", lambda _p, _i, entitlements_path=None: None)
    monkeypatch.setattr(ipa_mod.codesign, "verify", lambda _p: None)
    monkeypatch.setattr(ipa_mod.codesign, "extract_entitlements", lambda _p: None)
    monkeypatch.setattr(
        ipa_mod.codesign,
        "write_entitlements",
        lambda _e: str(tmp_path / "ents.plist"),
    )

    ipa_mod.resign_ipa(
        input_ipa=str(input_ipa),
        output_ipa=str(output_ipa),
        sign_identity="IDENTITY",
        profile_path="",
        entitlements_path="",
        main_app_name="",
        strict_entitlements=False,
        keep_temp=False,
        verbose=False,
        new_bundle_id="com.new.app",
        new_version="",
        new_build="",
        new_display_name="",
        ops=[],
        auto_rewrite_bundle_id_values=True,
    )

    with zipfile.ZipFile(output_ipa, "r") as zf:
        main_plist = plistlib.loads(zf.read("Payload/Main.app/Info.plist"))

    assert main_plist["CFBundleIdentifier"] == "com.new.app"
    assert main_plist["WKCompanionAppBundleIdentifier"] == "com.new.app.watch"
    assert main_plist["AlreadyNew"] == "com.new.app.watch"
    assert main_plist["Mixed"][0] == "com.new.app"
    assert main_plist["Mixed"][1] == "prefix.com.old.app"
    assert main_plist["Mixed"][2]["Deep"] == "com.new.app.ext"
