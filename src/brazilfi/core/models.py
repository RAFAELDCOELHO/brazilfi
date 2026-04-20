"""Pydantic models padronizados."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field


class SeriesPoint(BaseModel):
    """Um ponto de uma série temporal."""

    model_config = ConfigDict(frozen=True)

    date: date
    value: Decimal


class TimeSeries(BaseModel):
    """Série temporal padronizada (agnóstica ao provider)."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    code: str = Field(..., description="Código da série na fonte original")
    name: str = Field(..., description="Nome humano legível")
    unit: str = Field(default="", description="Unidade (%, BRL, etc.)")
    source: str = Field(..., description="Provider de origem (bacen, ibge, ...)")
    points: list[SeriesPoint]

    def to_dataframe(self) -> pd.DataFrame:
        """Converte para DataFrame pandas indexado por data."""
        if not self.points:
            return pd.DataFrame(columns=["value"])
        df = pd.DataFrame(
            [{"date": p.date, "value": float(p.value)} for p in self.points]
        )
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date")

    def __len__(self) -> int:
        return len(self.points)

    def __repr__(self) -> str:
        return (
            f"TimeSeries(name={self.name!r}, source={self.source!r}, "
            f"points={len(self.points)})"
        )
