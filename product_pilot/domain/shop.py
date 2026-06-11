"""Shop account configuration for merchant backend sessions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ShopAccount:
    name: str
    profile_dir: Path

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.name.strip():
            errors.append("shop name is required")
        if not str(self.profile_dir):
            errors.append("profile_dir is required")
        return errors


def parse_shop_accounts(text: str) -> tuple[list[ShopAccount], list[str]]:
    accounts: list[ShopAccount] = []
    errors: list[str] = []
    seen_names: set[str] = set()
    seen_profiles: set[Path] = set()

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 2:
            errors.append(f"line {line_number}: expected format `店铺名|Profile目录`")
            continue

        name, profile_value = parts
        profile_dir = Path(profile_value).expanduser()
        account = ShopAccount(name=name, profile_dir=profile_dir)
        account_errors = account.validate()
        if account_errors:
            errors.extend(f"line {line_number}: {error}" for error in account_errors)
            continue

        if account.name in seen_names:
            errors.append(f"line {line_number}: duplicate shop name `{account.name}`")
            continue
        resolved_profile = account.profile_dir.resolve()
        if resolved_profile in seen_profiles:
            errors.append(f"line {line_number}: duplicate profile dir `{account.profile_dir}`")
            continue

        seen_names.add(account.name)
        seen_profiles.add(resolved_profile)
        accounts.append(account)

    return accounts, errors
