"""Business logic services for Mwalimu context configuration."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models, transaction
from rest_framework.exceptions import ValidationError

from platform_api.apps.context.models import (
    GeographicUnit,
    GeographicUnitStatus,
    InstitutionContextRegion,
    UserFamiliarRegion,
)
from platform_api.apps.institutions.models import Institution, InstitutionStatus
from platform_api.apps.users.models import User


def create_user_familiar_region(
    user: User,
    geographic_unit_id: uuid.UUID | str,
    priority: int | None = None,
) -> UserFamiliarRegion:
    """Create a new familiar region preference for a user.

    If priority is omitted, assigns the next sequential priority.
    """
    try:
        geo_unit = GeographicUnit.objects.get(id=geographic_unit_id)
    except GeographicUnit.DoesNotExist as err:
        raise ValidationError(
            {"geographic_unit_id": "Geographic unit not found."}
        ) from err

    if geo_unit.status != GeographicUnitStatus.ACTIVE:
        raise ValidationError(
            {
                "geographic_unit_id": (
                    "Cannot select an archived geographic unit as a familiar region."
                )
            }
        )

    if UserFamiliarRegion.objects.filter(user=user, geographic_unit=geo_unit).exists():
        raise ValidationError(
            {
                "geographic_unit_id": (
                    "This geographic unit is already in your familiar regions."
                )
            }
        )

    if priority is None or priority < 1:
        current_max = (
            UserFamiliarRegion.objects.filter(user=user).aggregate(
                models_max=models.Max("priority")
            )["models_max"]
            or 0
        )
        priority = current_max + 1

    region = UserFamiliarRegion(
        user=user,
        geographic_unit=geo_unit,
        priority=priority,
    )
    try:
        region.clean()
    except DjangoValidationError as err:
        raise ValidationError(err.message_dict) from err

    region.save()
    return region


def reorder_user_familiar_regions(
    user: User,
    region_ids: Sequence[uuid.UUID | str],
) -> list[UserFamiliarRegion]:
    """Atomically reorder a user's familiar regions to priorities 1..N.

    Validates that:
    1. No duplicate IDs are supplied.
    2. All supplied IDs belong to the user.
    3. The submitted set exactly matches all the user's configured familiar regions.
    """
    parsed_ids = [uuid.UUID(str(rid)) for rid in region_ids]

    if len(parsed_ids) != len(set(parsed_ids)):
        raise ValidationError({"region_ids": "Duplicate region IDs are not allowed."})

    existing_regions = list(
        UserFamiliarRegion.objects.filter(user=user).select_related("geographic_unit")
    )
    existing_id_map = {r.id: r for r in existing_regions}

    if set(parsed_ids) != set(existing_id_map.keys()):
        raise ValidationError(
            {
                "region_ids": (
                    "Submitted region IDs must match exactly all configured "
                    "familiar regions for this user."
                )
            }
        )

    with transaction.atomic():
        updated_regions: list[UserFamiliarRegion] = []
        for index, rid in enumerate(parsed_ids, start=1):
            region = existing_id_map[rid]
            if region.priority != index:
                region.priority = index
                region.save(update_fields=["priority", "updated_at"])
            updated_regions.append(region)

    updated_regions.sort(key=lambda r: r.priority)
    return updated_regions


def create_institution_context_region(
    institution_id: uuid.UUID | str,
    geographic_unit_id: uuid.UUID | str,
    priority: int | None = None,
) -> InstitutionContextRegion:
    """Create a new context region focus for an institution.

    If priority is omitted, assigns the next sequential priority.
    """
    try:
        institution = Institution.objects.get(id=institution_id)
    except Institution.DoesNotExist as err:
        raise ValidationError({"institution_id": "Institution not found."}) from err

    if institution.status != InstitutionStatus.ACTIVE:
        raise ValidationError({"institution_id": "Institution is not active."})

    try:
        geo_unit = GeographicUnit.objects.get(id=geographic_unit_id)
    except GeographicUnit.DoesNotExist as err:
        raise ValidationError(
            {"geographic_unit_id": "Geographic unit not found."}
        ) from err

    if geo_unit.status != GeographicUnitStatus.ACTIVE:
        raise ValidationError(
            {
                "geographic_unit_id": (
                    "Cannot select an archived geographic unit as an "
                    "institution context region."
                )
            }
        )

    if InstitutionContextRegion.objects.filter(
        institution=institution, geographic_unit=geo_unit
    ).exists():
        raise ValidationError(
            {
                "geographic_unit_id": (
                    "This geographic unit is already configured for this institution."
                )
            }
        )

    if priority is None or priority < 1:
        current_max = (
            InstitutionContextRegion.objects.filter(institution=institution).aggregate(
                models_max=models.Max("priority")
            )["models_max"]
            or 0
        )
        priority = current_max + 1

    region = InstitutionContextRegion(
        institution=institution,
        geographic_unit=geo_unit,
        priority=priority,
    )
    try:
        region.clean()
    except DjangoValidationError as err:
        raise ValidationError(err.message_dict) from err

    region.save()
    return region


def reorder_institution_context_regions(
    institution_id: uuid.UUID | str,
    region_ids: Sequence[uuid.UUID | str],
) -> list[InstitutionContextRegion]:
    """Atomically reorder an institution's context regions to priorities 1..N.

    Validates that:
    1. No duplicate IDs are supplied.
    2. All supplied IDs belong to the institution.
    3. The submitted set exactly matches all the institution's configured regions.
    """
    parsed_ids = [uuid.UUID(str(rid)) for rid in region_ids]

    if len(parsed_ids) != len(set(parsed_ids)):
        raise ValidationError({"region_ids": "Duplicate region IDs are not allowed."})

    existing_regions = list(
        InstitutionContextRegion.objects.filter(
            institution_id=institution_id
        ).select_related("geographic_unit")
    )
    existing_id_map = {r.id: r for r in existing_regions}

    if set(parsed_ids) != set(existing_id_map.keys()):
        raise ValidationError(
            {
                "region_ids": (
                    "Submitted region IDs must match exactly all configured "
                    "context regions for this institution."
                )
            }
        )

    with transaction.atomic():
        updated_regions: list[InstitutionContextRegion] = []
        for index, rid in enumerate(parsed_ids, start=1):
            region = existing_id_map[rid]
            if region.priority != index:
                region.priority = index
                region.save(update_fields=["priority", "updated_at"])
            updated_regions.append(region)

    updated_regions.sort(key=lambda r: r.priority)
    return updated_regions
