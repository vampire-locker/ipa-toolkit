import hashlib

from ipa_toolkit import provisioning
from ipa_toolkit.provisioning import ProvisioningProfile


def test_profile_certificate_sha1s_extracts_unique_hashes() -> None:
    cert_a = b"cert-a"
    cert_b = b"cert-b"
    profile = ProvisioningProfile(
        raw={"DeveloperCertificates": [cert_a, cert_b, cert_a, "skip"]},
        team_id="TEAM123",
        entitlements={},
    )

    got = provisioning.profile_certificate_sha1s(profile)
    want = [
        hashlib.sha1(cert_a).hexdigest().upper(),
        hashlib.sha1(cert_b).hexdigest().upper(),
    ]
    assert got == want


def test_list_codesigning_identities_parses_security_output(monkeypatch) -> None:
    monkeypatch.setattr(
        provisioning,
        "_run",
        lambda _cmd: (
            b'  1) ABCDEF0123456789ABCDEF0123456789ABCDEF01 "Apple Distribution: A (TEAM)"\n'
            b"  2) not-a-match\n"
            b'  3) 00112233445566778899AABBCCDDEEFF00112233 "Apple Development: B (TEAM)"\n'
        ),
    )

    got = provisioning.list_codesigning_identities()
    assert got == [
        ("ABCDEF0123456789ABCDEF0123456789ABCDEF01", "Apple Distribution: A (TEAM)"),
        ("00112233445566778899AABBCCDDEEFF00112233", "Apple Development: B (TEAM)"),
    ]


def test_resolve_sign_identity_prefers_keychain_name(monkeypatch) -> None:
    cert = b"cert"
    cert_hash = hashlib.sha1(cert).hexdigest().upper()
    profile = ProvisioningProfile(
        raw={"DeveloperCertificates": [cert]},
        team_id="TEAM123",
        entitlements={},
    )
    monkeypatch.setattr(
        provisioning,
        "list_codesigning_identities",
        lambda: [(cert_hash, "Apple Distribution: Example (TEAM123)")],
    )

    got = provisioning.resolve_sign_identity_from_profile(profile)
    assert got == "Apple Distribution: Example (TEAM123)"


def test_resolve_sign_identity_falls_back_to_hash(monkeypatch) -> None:
    cert = b"cert"
    cert_hash = hashlib.sha1(cert).hexdigest().upper()
    profile = ProvisioningProfile(
        raw={"DeveloperCertificates": [cert]},
        team_id="TEAM123",
        entitlements={},
    )
    monkeypatch.setattr(provisioning, "list_codesigning_identities", lambda: [])

    got = provisioning.resolve_sign_identity_from_profile(profile)
    assert got == cert_hash
