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


# --- Bonds (Tesouro Direto) ---


class Bond(BaseModel):
    """Título público disponível para compra/resgate."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Nome comercial (ex: 'Tesouro Prefixado 2027')")
    bond_type: str = Field(..., description="Tipo: LTN, NTN-B, NTN-F, LFT, NTN-B Principal")
    maturity: date = Field(..., description="Data de vencimento")
    index: str | None = Field(None, description="Indexador: SELIC, IPCA, Prefixado")
    buy_rate: Decimal | None = Field(None, description="Taxa compra (% a.a.)")
    sell_rate: Decimal | None = Field(None, description="Taxa venda (% a.a.)")
    buy_price: Decimal | None = Field(None, description="Preço compra (BRL)")
    sell_price: Decimal | None = Field(None, description="Preço venda (BRL)")
    min_investment: Decimal | None = Field(None, description="Investimento mínimo (BRL)")
    isin: str | None = Field(None, description="Código ISIN")
    available: bool = Field(True, description="Está disponível para compra")


class BondQuote(BaseModel):
    """Ponto histórico de cotação de um título."""

    model_config = ConfigDict(frozen=True)

    date: date
    bond_type: str
    maturity: date
    buy_rate: Decimal | None = None
    sell_rate: Decimal | None = None
    buy_price: Decimal | None = None
    sell_price: Decimal | None = None
