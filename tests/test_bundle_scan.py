from ipa_toolkit.bundle_scan import bundle_new_id_for, find_bundles_under


def test_bundle_new_id_for_rewrites_main_and_prefix() -> None:
    assert bundle_new_id_for("com.old.app", "com.old.app", "com.new.app") == "com.new.app"
    assert (
        bundle_new_id_for("com.old.app.share", "com.old.app", "com.new.app")
        == "com.new.app.share"
    )


def test_bundle_new_id_for_keeps_non_prefix_bundle() -> None:
    assert bundle_new_id_for("com.other.app", "com.old.app", "com.new.app") == "com.other.app"


def test_find_bundles_under_includes_main_app_first(tmp_path) -> None:
    app = tmp_path / "Main.app"
    appex = app / "PlugIns" / "Share.appex"
    nested = appex / "Nested.app"
    app.mkdir()
    nested.mkdir(parents=True)

    bundles = find_bundles_under(str(app))

    assert bundles[0] == str(app)
    assert str(appex) in bundles
    assert str(nested) in bundles
