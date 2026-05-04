"""Request / tenancy context carried through job submission (SaaS-ready, optional locally)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class JobRequestContext:
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None

    def to_metadata_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        if self.tenant_id is not None:
            d["tenant_id"] = self.tenant_id
        if self.user_id is not None:
            d["user_id"] = self.user_id
        return d

    @staticmethod
    def from_optional_dict(data: Optional[Dict[str, Any]]) -> "JobRequestContext":
        if not data:
            return JobRequestContext()
        return JobRequestContext(
            tenant_id=data.get("tenant_id"),
            user_id=data.get("user_id"),
        )
