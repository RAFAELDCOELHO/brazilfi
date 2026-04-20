"""Testes do provider Tesouro Direto (via CSV Tesouro Transparente)."""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from brazilfi.core.exceptions import DataNotFoundError
from brazilfi.providers.tesouro import TesouroDireto

# Mock do CSV já normalizado (como _load_historico retornaria)
FAKE_HISTORICO = pd.DataFrame({
    "bond_type": [
        "Tesouro Prefixado",
        "Tesouro IPCA+ com Juros Semestrais",
        "Tesouro Selic",
        "Tesouro Prefixado",  # dado mais antigo, deve ser filtrado
    ],
    "maturity": pd.to_datetime([
        "2027-01-01",
        "2029-05-15",
        "2031-03-01",
        "2027-01-01",
    ]),
    "date": pd.to_datetime([
        "2026-04-19",
        "2026-04-19",
        "2026-04-19",
        "2024-01-02",  # antigo
    ]),
    "buy_rate": [11.25, 6.50, 0.04, 10.00],
    "sell_rate": [11.50, 6.75, 0.04, 10.10],
    "buy_price": [850.34, 3200.11, 15000.00, 900.00],
    "sell_price": [851.00, 3205.00, 15000.00, 901.00],
})


@patch.object(TesouroDireto, "_load_historico")
def test_available_returns_bonds(mock_load) -> None:
    mock_load.return_value = FAKE_HISTORICO
    bonds = TesouroDireto().available()
    # Só os 3 da data mais recente
    assert len(bonds) == 3
    names = [b.name for b in bonds]
    assert any("Prefixado 2027" in n for n in names)


@patch.object(TesouroDireto, "_load_historico")
def test_bond_type_inference(mock_load) -> None:
    mock_load.return_value = FAKE_HISTORICO
    bonds = TesouroDireto().available()
    types = {b.bond_type for b in bonds}
    assert "LTN" in types
    assert "NTN-B" in types
    assert "LFT" in types


@patch.object(TesouroDireto, "_load_historico")
def test_index_inference(mock_load) -> None:
    mock_load.return_value = FAKE_HISTORICO
    bonds = TesouroDireto().available()
    indices = {b.index for b in bonds}
    assert "Prefixado" in indices
    assert "IPCA" in indices
    assert "SELIC" in indices


@patch.object(TesouroDireto, "_load_historico")
def test_available_dataframe(mock_load) -> None:
    mock_load.return_value = FAKE_HISTORICO
    df = TesouroDireto().available_dataframe()
    assert len(df) == 3
    assert "bond_type" in df.columns
    assert "maturity" in df.columns


@patch.object(TesouroDireto, "_load_historico")
def test_empty_raises(mock_load) -> None:
    # DataFrame válido mas sem títulos ativos na última data
    empty_df = pd.DataFrame({
        "bond_type": ["Tesouro Prefixado"],
        "maturity": pd.to_datetime(["2020-01-01"]),  # vencido
        "date": pd.to_datetime(["2026-04-19"]),
        "buy_rate": [10.0],
        "sell_rate": [10.0],
        "buy_price": [1000.0],
        "sell_price": [1000.0],
    })
    mock_load.return_value = empty_df
    with pytest.raises(DataNotFoundError):
        TesouroDireto().available()
