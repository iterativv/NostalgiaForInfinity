"""Validated request and transition records."""

from datetime import datetime
from enum import StrEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, AwareDatetime


class Phase(StrEnum):
  REQUESTED = "requested"
  CLOSING = "closing"
  READY = "ready"
  ADMITTED = "admitted"
  REVIEW = "review"
  COMPLETE = "complete"
  CANCELLED = "cancelled"
  REJECTED = "rejected"


TERMINAL: Final = (Phase.COMPLETE, Phase.CANCELLED, Phase.REJECTED)
LINK_KEY: Final = "pair_switch_v1"
TAG_PREFIX: Final = "ps_"


class SwitchError(RuntimeError):
  """A request was refused without placing an order."""


class Request(BaseModel):
  model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
  token: str = Field(pattern=r"^[a-f0-9]{32}$")
  source_id: int = Field(gt=0)
  target: str = Field(min_length=3, max_length=25)
  stake: float = Field(gt=0)
  profit_buffer: float = Field(default=0, ge=0)
  expires_at: AwareDatetime


class Intent(BaseModel):
  model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
  request: Request
  phase: Phase = Phase.REQUESTED
  revision: int = 0
  source_pair: str = ""
  source_open: datetime | None = None
  short: bool = False
  leverage: float = 1.0
  source_stake: float = 0.0
  carry_profit: float = 0.0
  budget: float = 0.0
  target_id: int | None = None
  exit_admitted: bool = False
  note: str = ""

  @property
  def tag(self) -> str:
    return TAG_PREFIX + self.request.token


class Link(BaseModel):
  model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
  token: str
  source_id: int
  carry_profit: float
  profit_buffer: float
