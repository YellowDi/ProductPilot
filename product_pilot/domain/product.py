"""Product draft domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProductImage:
    path: Path
    role: str = "gallery"

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "ProductImage":
        return cls(
            path=Path(str(payload.get("path", ""))),
            role=str(payload.get("role", "gallery")),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not str(self.path):
            errors.append("image.path is required")
        if self.role not in {"main", "gallery", "detail"}:
            errors.append(f"image.role must be one of main, gallery, detail: {self.role}")
        return errors


@dataclass(frozen=True)
class ProductSku:
    name: str
    price: Decimal
    stock: int

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "ProductSku":
        return cls(
            name=str(payload.get("name", "")).strip(),
            price=_to_decimal(payload.get("price")),
            stock=_to_int(payload.get("stock")),
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.name:
            errors.append("sku.name is required")
        if self.price <= Decimal("0"):
            errors.append(f"sku.price must be greater than 0: {self.name or '<empty>'}")
        if self.stock < 0:
            errors.append(f"sku.stock must be greater than or equal to 0: {self.name or '<empty>'}")
        return errors


@dataclass(frozen=True)
class ProductDraft:
    title: str
    category: str
    images: list[ProductImage] = field(default_factory=list)
    skus: list[ProductSku] = field(default_factory=list)
    description: str = ""

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "ProductDraft":
        images_payload = payload.get("images", [])
        skus_payload = payload.get("skus", [])

        return cls(
            title=str(payload.get("title", "")).strip(),
            category=str(payload.get("category", "")).strip(),
            description=str(payload.get("description", "")).strip(),
            images=[
                ProductImage.from_mapping(item)
                for item in images_payload
                if isinstance(item, dict)
            ],
            skus=[
                ProductSku.from_mapping(item)
                for item in skus_payload
                if isinstance(item, dict)
            ],
        )

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.title:
            errors.append("title is required")
        if len(self.title) > 60:
            errors.append("title must be at most 60 characters")
        if not self.category:
            errors.append("category is required")
        if not self.images:
            errors.append("at least one image is required")
        if not any(image.role == "main" for image in self.images):
            errors.append("at least one main image is required")
        if not self.skus:
            errors.append("at least one sku is required")

        for index, image in enumerate(self.images, start=1):
            errors.extend(f"images[{index}].{error}" for error in image.validate())
        for index, sku in enumerate(self.skus, start=1):
            errors.extend(f"skus[{index}].{error}" for error in sku.validate())

        return errors


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1
