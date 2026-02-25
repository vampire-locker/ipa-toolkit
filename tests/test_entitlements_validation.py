from ipa_toolkit.entitlements import validate_entitlements_for_bundle


def test_validate_entitlements_accepts_matching_identifiers() -> None:
    ent = {
        "application-identifier": "TEAM123.com.new.app",
        "com.apple.application-identifier": "TEAM123.com.new.app",
        "keychain-access-groups": ["TEAM123.com.new.app", "TEAM123.shared"],
    }
    validate_entitlements_for_bundle(
        "Payload/App.app",
        ent,
        old_bundle_id="com.old.app",
        new_bundle_id="com.new.app",
        profile_team_id="TEAM123",
    )


def test_validate_entitlements_rejects_mismatched_app_identifiers() -> None:
    ent = {
        "application-identifier": "TEAM123.com.new.app",
        "com.apple.application-identifier": "TEAM123.com.other.app",
    }
    try:
        validate_entitlements_for_bundle(
            "Payload/App.app",
            ent,
            old_bundle_id="com.old.app",
            new_bundle_id="com.new.app",
            profile_team_id="TEAM123",
        )
        raise AssertionError("expected SystemExit")
    except SystemExit as e:
        msg = str(e)
        assert "must match" in msg


def test_validate_entitlements_rejects_wrong_expected_app_id() -> None:
    ent = {"application-identifier": "TEAM123.com.wrong.app"}
    try:
        validate_entitlements_for_bundle(
            "Payload/App.app",
            ent,
            old_bundle_id="com.old.app",
            new_bundle_id="com.new.app",
            profile_team_id="TEAM123",
        )
        raise AssertionError("expected SystemExit")
    except SystemExit as e:
        msg = str(e)
        assert "expected TEAM123.com.new.app" in msg


def test_validate_entitlements_rejects_stale_keychain_prefix() -> None:
    ent = {
        "application-identifier": "TEAM123.com.new.app",
        "keychain-access-groups": [
            "TEAM123.com.old.app",
            "TEAM123.com.new.app.shared",
        ],
    }
    try:
        validate_entitlements_for_bundle(
            "Payload/App.app",
            ent,
            old_bundle_id="com.old.app",
            new_bundle_id="com.new.app",
            profile_team_id="TEAM123",
        )
        raise AssertionError("expected SystemExit")
    except SystemExit as e:
        msg = str(e)
        assert "old bundle prefix TEAM123.com.old.app" in msg


def test_validate_entitlements_rejects_non_list_keychain_groups() -> None:
    ent = {
        "application-identifier": "TEAM123.com.new.app",
        "keychain-access-groups": "TEAM123.com.new.app",
    }
    try:
        validate_entitlements_for_bundle(
            "Payload/App.app",
            ent,
            old_bundle_id="com.old.app",
            new_bundle_id="com.new.app",
            profile_team_id="TEAM123",
        )
        raise AssertionError("expected SystemExit")
    except SystemExit as e:
        msg = str(e)
        assert "must be an array" in msg


def test_validate_entitlements_strict_rejects_missing_app_identifier() -> None:
    ent = {"keychain-access-groups": ["TEAM123.com.new.app"]}
    try:
        validate_entitlements_for_bundle(
            "Payload/App.app",
            ent,
            old_bundle_id="com.old.app",
            new_bundle_id="com.new.app",
            profile_team_id="TEAM123",
            require_app_identifier=True,
        )
        raise AssertionError("expected SystemExit")
    except SystemExit as e:
        msg = str(e)
        assert "missing application-identifier" in msg
