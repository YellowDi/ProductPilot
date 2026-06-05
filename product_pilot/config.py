"""Runtime configuration model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    merchant_backend_url: str
    chrome_profile_dir: Path
    artifacts_dir: Path

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.merchant_backend_url.startswith(("http://", "https://")):
            errors.append("merchant_backend_url must be an http or https URL")
        if not str(self.chrome_profile_dir):
            errors.append("chrome_profile_dir is required")
        if not str(self.artifacts_dir):
            errors.append("artifacts_dir is required")
        return errors

