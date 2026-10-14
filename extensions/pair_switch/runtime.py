"""Runtime binding and data-readiness checks for a single bot owner."""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from freqtrade.data.dataprovider import DataProvider
from sqlalchemy.engine import make_url


class Options(BaseModel):
  model_config = ConfigDict(frozen=True, extra="forbid")
  database: Path
  allow_live: bool = False


def bot_binding(db_url: str, exchange: str, dry_run: bool) -> str:
  url = make_url(db_url)
  if url.drivername == "sqlite" and url.database and url.database != ":memory:":
    db_url = str(url.set(database=str(Path(url.database).resolve())))
  return hashlib.sha256(json.dumps([db_url, exchange, dry_run]).encode()).hexdigest()


def available_pairs(dp: DataProvider, now: datetime, stake_currency: str) -> set[str]:
  result: set[str] = set()
  for pair in dp.current_whitelist():
    if "/" not in pair or pair.split("/", 1)[1].split(":", 1)[0] != stake_currency:
      continue
    market = dp.market(pair)
    if not market or market.get("active") is not True:
      continue
    frame, _ = dp.get_analyzed_dataframe(pair, "5m")
    if frame.empty:
      continue
    candle = frame.iloc[-1]
    age = now - candle["date"].to_pydatetime()
    if timedelta(0) <= age <= timedelta(minutes=10) and candle["close"] > 0 and candle["volume"] > 0:
      result.add(pair)
  return result
