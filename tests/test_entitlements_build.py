from ipa_toolkit.entitlements import build_entitlements_by_bundle
from ipa_toolkit.provisioning import ProvisioningProfile


def test_build_entitlements_prefers_explicit_and_validates() -> None:
    bundles = ["/app/Main.app"]
    bundle_ids = {"/app/Main.app": ("com.old.app", "com.new.app")}
    explicit = {
        "application-identifier": "TEAM123.com.new.app",
        "com.apple.application-identifier": "TEAM123.com.new.app",
    }

    out = build_entitlements_by_bundle(
        bundles=bundles,
        bundle_ids=bundle_ids,
        explicit_entitlements=explicit,
        profile=ProvisioningProfile(raw={}, team_id="TEAM123", entitlements={}),
        extract_entitlements=lambda _b: {"application-identifier": "TEAM123.com.bad"},
    )

    assert out["/app/Main.app"]["application-identifier"] == "TEAM123.com.new.app"


def test_build_entitlements_fallbacks_to_profile_then_rewrites() -> None:
    bundles = ["/app/Main.app", "/app/Main.app/PlugIns/Share.appex"]
    bundle_ids = {
        "/app/Main.app": ("com.old.app", "com.new.app"),
        "/app/Main.app/PlugIns/Share.appex": ("com.old.app.share", "com.new.app.share"),
    }
    profile = ProvisioningProfile(
        raw={},
        team_id="TEAM123",
        entitlements={
            "application-identifier": "TEAM123.com.old.app",
            "com.apple.application-identifier": "TEAM123.com.old.app",
            "keychain-access-groups": ["TEAM123.com.old.app", "TEAM123.shared"],
        },
    )

    out = build_entitlements_by_bundle(
        bundles=bundles,
        bundle_ids=bundle_ids,
        explicit_entitlements=None,
        profile=profile,
        extract_entitlements=lambda _b: None,
    )

    assert out["/app/Main.app"]["application-identifier"] == "TEAM123.com.new.app"
    assert (
        out["/app/Main.app/PlugIns/Share.appex"]["application-identifier"]
        == "TEAM123.com.new.app.share"
    )


def test_build_entitlements_keeps_none_when_no_source() -> None:
    out = build_entitlements_by_bundle(
        bundles=["/app/Main.app"],
        bundle_ids={"/app/Main.app": ("com.old.app", "com.new.app")},
        explicit_entitlements=None,
        profile=None,
        extract_entitlements=lambda _b: None,
    )
    assert out["/app/Main.app"] is None


def test_build_entitlements_strict_rejects_missing_app_identifier() -> None:
    try:
        build_entitlements_by_bundle(
            bundles=["/app/Main.app"],
            bundle_ids={"/app/Main.app": ("com.old.app", "com.new.app")},
            explicit_entitlements={"keychain-access-groups": ["TEAM123.com.new.app"]},
            profile=None,
            extract_entitlements=lambda _b: None,
            require_app_identifier=True,
        )
        assert False, "expected SystemExit"
    except SystemExit as e:
        assert "missing application-identifier" in str(e)
