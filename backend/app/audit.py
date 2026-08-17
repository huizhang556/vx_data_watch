from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog, User


def write_audit(
    db: Session,
    action: str,
    user: User | None = None,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details_json=json.dumps(details, ensure_ascii=False, separators=(",", ":"))
            if details
            else None,
        )
    )
