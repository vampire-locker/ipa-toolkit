from __future__ import annotations

"""
签名权限（`entitlements`）重写与校验辅助模块。

将应用标识与钥匙串分组规则独立出来，便于复用与单元测试。
"""

from collections.abc import Callable, Sequence
from typing import Any

from .provisioning import ProvisioningProfile


def adjust_entitlements_for_bundle(
    ent: dict,
    *,
    team_id: str,
    old_bundle_id: str,
    new_bundle_id: str,
) -> dict:
    """按新包标识重写应用标识与钥匙串访问组前缀。"""
    if not team_id or old_bundle_id == new_bundle_id:
        return ent

    out = dict(ent)
    new_prefix = f"{team_id}.{new_bundle_id}"

    for key in ("application-identifier", "com.apple.application-identifier"):
        if key in out:
            out[key] = new_prefix

    kag = out.get("keychain-access-groups")
    if isinstance(kag, list):
        old_prefix = f"{team_id}.{old_bundle_id}"
        new_kag = []
        for item in kag:
            if isinstance(item, str) and item.startswith(old_prefix):
                new_kag.append(new_prefix + item[len(old_prefix):])
            else:
                new_kag.append(item)
        out["keychain-access-groups"] = new_kag

    return out


def _team_id_from_app_identifier(value: object) -> str:
    """从 `TEAMID.bundle.id` 形式的标识里提取 TEAMID。"""
    if not isinstance(value, str) or "." not in value:
        return ""
    return value.split(".", 1)[0].strip()


def validate_entitlements_for_bundle(
    bundle_path: str,
    ent: dict | None,
    *,
    old_bundle_id: str,
    new_bundle_id: str,
    profile_team_id: str,
    require_app_identifier: bool = False,
) -> None:
    """校验单个应用包的签名权限关键字段一致性。"""
    if ent is None:
        return

    errors: list[str] = []
    app_ids: dict[str, str] = {}

    for key in ("application-identifier", "com.apple.application-identifier"):
        if key not in ent:
            continue
        value = ent.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{key} must be a non-empty string")
            continue
        app_ids[key] = value.strip()

    if require_app_identifier and not app_ids:
        errors.append(
            "missing application-identifier/com.apple.application-identifier"
        )

    if len(set(app_ids.values())) > 1:
        errors.append(
            "application-identifier and com.apple.application-identifier must match"
        )

    team_id = profile_team_id.strip() if profile_team_id else ""
    if not team_id:
        for value in app_ids.values():
            team_id = _team_id_from_app_identifier(value)
            if team_id:
                break

    expected_app_id = f"{team_id}.{new_bundle_id}" if team_id and new_bundle_id else ""
    if expected_app_id:
        for key, value in app_ids.items():
            if value != expected_app_id:
                errors.append(
                    f"{key} mismatch: expected {expected_app_id}, got {value}"
                )

    kag = ent.get("keychain-access-groups")
    if kag is not None:
        if not isinstance(kag, list):
            errors.append("keychain-access-groups must be an array")
        else:
            for i, item in enumerate(kag):
                if not isinstance(item, str):
                    errors.append(f"keychain-access-groups[{i}] must be a string")

            if team_id and old_bundle_id and new_bundle_id and old_bundle_id != new_bundle_id:
                old_prefix = f"{team_id}.{old_bundle_id}"
                stale = [x for x in kag if isinstance(x, str) and x.startswith(old_prefix)]
                if stale:
                    errors.append(
                        f"keychain-access-groups contains old bundle prefix {old_prefix}"
                    )

    if errors:
        detail = "\n  - ".join(errors)
        raise SystemExit(
            f"Error: invalid entitlements for bundle {bundle_path}:\n  - {detail}"
        )


def build_entitlements_by_bundle(
    *,
    bundles: Sequence[str],
    bundle_ids: dict[str, tuple[str, str]],
    explicit_entitlements: dict | None,
    profile: ProvisioningProfile | None,
    extract_entitlements: Callable[[str], dict[str, Any] | None],
    require_app_identifier: bool = False,
) -> dict[str, dict | None]:
    """为所有应用包构建最终签名权限映射（含重写与校验）。"""
    ent_by_bundle: dict[str, dict | None] = {}

    for bundle_path in bundles:
        ent: dict | None = None

        if explicit_entitlements is not None:
            ent = explicit_entitlements
        else:
            ent = extract_entitlements(bundle_path)
            if ent is None and profile is not None:
                ent = dict(profile.entitlements)
            if ent is None:
                ent_by_bundle[bundle_path] = None
                continue

        if profile is not None and bundle_path in bundle_ids:
            old_id, new_id = bundle_ids[bundle_path]
            ent = adjust_entitlements_for_bundle(
                ent,
                team_id=profile.team_id,
                old_bundle_id=old_id,
                new_bundle_id=new_id,
            )

        if bundle_path in bundle_ids:
            old_id, new_id = bundle_ids[bundle_path]
            validate_entitlements_for_bundle(
                bundle_path,
                ent,
                old_bundle_id=old_id,
                new_bundle_id=new_id,
                profile_team_id=profile.team_id if profile is not None else "",
                require_app_identifier=require_app_identifier,
            )

        ent_by_bundle[bundle_path] = ent

    return ent_by_bundle
