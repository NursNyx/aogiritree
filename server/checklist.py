from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class CriterionType(str, Enum):
    BOOLEAN = "boolean"
    SCALE = "scale"


class CriterionConfig(BaseModel):
    criterion_id: str = Field(..., min_length=1)
    type: CriterionType
    weight: float = Field(..., ge=0)
    na_allowed: bool = False
    scale: Optional[List[int]] = None

    @model_validator(mode="after")
    def validate_scale(self) -> "CriterionConfig":
        if self.type == CriterionType.SCALE:
            if not self.scale:
                raise ValueError("scale criteria must provide scale values")
            if sorted(self.scale) != self.scale:
                raise ValueError("scale values must be sorted")
        else:
            self.scale = None
        return self


class ChecklistConfig(BaseModel):
    criteria: List[CriterionConfig] = Field(default_factory=list)
