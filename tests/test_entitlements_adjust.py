from ipa_toolkit.entitlements import adjust_entitlements_for_bundle


def test_adjust_entitlements_rewrites_app_identifier_fields() -> None:
    ent = {
        "application-identifier": "TEAM123.com.old.app",
        "com.apple.application-identifier": "TEAM123.com.old.app",
    }

    out = adjust_entitlements_for_bundle(
        ent,
        team_id="TEAM123",
        old_bundle_id="com.old.app",
        new_bundle_id="com.new.app",
    )

    assert out["application-identifier"] == "TEAM123.com.new.app"
    assert out["com.apple.application-identifier"] == "TEAM123.com.new.app"


def test_adjust_entitlements_rewrites_keychain_group_prefix() -> None:
    ent = {
        "keychain-access-groups": [
            "TEAM123.com.old.app",
            "TEAM123.com.old.app.shared",
            "TEAM123.other",
        ]
    }

    out = adjust_entitlements_for_bundle(
        ent,
        team_id="TEAM123",
        old_bundle_id="com.old.app",
        new_bundle_id="com.new.app",
    )

    assert out["keychain-access-groups"] == [
        "TEAM123.com.new.app",
        "TEAM123.com.new.app.shared",
        "TEAM123.other",
    ]


def test_adjust_entitlements_noop_when_team_missing_or_id_unchanged() -> None:
    ent = {"application-identifier": "TEAM123.com.old.app"}
    out_no_team = adjust_entitlements_for_bundle(
        ent,
        team_id="",
        old_bundle_id="com.old.app",
        new_bundle_id="com.new.app",
    )
    out_same_id = adjust_entitlements_for_bundle(
        ent,
        team_id="TEAM123",
        old_bundle_id="com.old.app",
        new_bundle_id="com.old.app",
    )

    assert out_no_team == ent
    assert out_same_id == ent
