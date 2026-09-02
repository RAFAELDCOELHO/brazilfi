"""Provider ANBIMA — curva de juros do IMA (Índice de Mercado ANBIMA)."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd

from brazilfi.core.exceptions import DataNotFoundError
from brazilfi.core.http_client import HttpClient
from brazilfi.core.models import CurvePoint, YieldCurve

# Arquivo completo do IMA do último dia útil divulgado, linkado como "TXT" em
# https://www.anbima.com.br/informacoes/ima/ima.asp (seção "IMA arquivos completos").
# Traz TOTAIS (registro 1) e COMPOSIÇÃO DE CARTEIRA (registro 2) de toda a
# família IMA, delimitado por "@" e codificado em latin-1.
IMA_COMPLETO_TXT = "https://www.anbima.com.br/informacoes/ima/arqs/ima_completo.txt"

# Escopo desta versão: apenas o IMA-B total. IMA-B 5 e IMA-B 5+ vêm depois.
IMA_B = "IMA-B"

DELIMITER = "@"
NULL_MARKER = "--"
ENCODING = "latin-1"

# O site da ANBIMA rejeita clientes sem cabeçalhos de navegador.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/plain, text/html, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": "https://www.anbima.com.br/informacoes/ima/ima.asp",
}

# Posições dos campos no registro 1 (TOTAIS).
TOT_DATE = 1
TOT_INDEX = 2
TOT_INDEX_NUMBER = 3
TOT_DAILY_CHANGE = 4
TOT_DURATION = 9

# Posições dos campos no registro 2 (COMPOSIÇÃO DE CARTEIRA).
CART_DATE = 1
CART_INDEX = 2
CART_BOND_TYPE = 3
CART_MATURITY = 4
CART_SELIC_CODE = 5
CART_ISIN = 6
CART_RATE = 7
CART_PRICE = 8
CART_WEIGHT = 13
CART_BUSINESS_DAYS = 14
CART_DURATION = 15
CART_MIN_FIELDS = 16


class ANBIMA:
    """
    Wrapper para os índices de mercado da ANBIMA.

    Exemplos:
        >>> an = ANBIMA()
        >>> curva = an.curva_ima()               # curva IMA-B do último dia útil
        >>> curva.points[0].rate                 # taxa indicativa do vértice curto
        >>> df = an.curva_ima_dataframe()        # mesmo, como DataFrame
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self.client = HttpClient(timeout=timeout, headers=BROWSER_HEADERS)

    # ---------- Curva IMA-B ----------

    def curva_ima(self) -> YieldCurve:
        """
        Curva de juros do IMA-B (total) no último dia útil divulgado.

        Cada vértice é uma NTN-B que compõe a carteira teórica do índice, com a
        taxa indicativa ANBIMA (% a.a.), PU, peso e duration. Os agregados do
        índice (número-índice, variação diária, duration) vêm do bloco TOTAIS
        do mesmo arquivo.

        Somente o IMA-B total é retornado; IMA-B 5 e IMA-B 5+ ficam para uma
        expansão posterior.
        """
        rows = self._fetch_rows()
        points = self._parse_points(rows, IMA_B)
        if not points:
            raise DataNotFoundError(
                f"Arquivo completo do IMA sem composição de carteira para {IMA_B}"
            )

        totals = self._parse_totals(rows, IMA_B)
        reference_date = (
            self._to_date(totals[TOT_DATE])
            if totals
            else self._to_date(self._first_index_row(rows, IMA_B)[CART_DATE])
        )
        if reference_date is None:
            raise DataNotFoundError("Arquivo completo do IMA sem data de referência")

        return YieldCurve(
            index=IMA_B,
            reference_date=reference_date,
            source="anbima",
            index_number=self._to_decimal(totals[TOT_INDEX_NUMBER]) if totals else None,
            daily_change_pct=(
                self._to_decimal(totals[TOT_DAILY_CHANGE]) if totals else None
            ),
            duration_days=self._to_int(totals[TOT_DURATION]) if totals else None,
            points=points,
        )

    def curva_ima_dataframe(self) -> pd.DataFrame:
        """Mesmo que `curva_ima()`, mas como DataFrame indexado por vencimento."""
        return self.curva_ima().to_dataframe()

    # ---------- Internals ----------

    def _fetch_rows(self) -> list[list[str]]:
        """Baixa o TXT completo do IMA e quebra em campos por linha."""
        raw = self.client.get_text(IMA_COMPLETO_TXT, encoding=ENCODING)
        rows: list[list[str]] = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            rows.append([field.strip() for field in line.split(DELIMITER)])
        if not rows:
            raise DataNotFoundError("Arquivo completo do IMA veio vazio")
        return rows

    @classmethod
    def _parse_totals(cls, rows: list[list[str]], index: str) -> list[str] | None:
        """Registro 1 (TOTAIS) do índice pedido, ou None se ausente."""
        for row in rows:
            if (
                row[0] == "1"
                and len(row) > TOT_DURATION
                and cls._same_index(row[TOT_INDEX], index)
                and cls._to_date(row[TOT_DATE]) is not None
            ):
                return row
        return None

    @classmethod
    def _parse_points(cls, rows: list[list[str]], index: str) -> list[CurvePoint]:
        """Registros 2 (COMPOSIÇÃO DE CARTEIRA) do índice pedido, como vértices."""
        points: list[CurvePoint] = []
        for row in rows:
            if row[0] != "2" or len(row) < CART_MIN_FIELDS:
                continue
            if not cls._same_index(row[CART_INDEX], index):
                continue
            maturity = cls._to_date(row[CART_MATURITY])
            rate = cls._to_decimal(row[CART_RATE])
            if maturity is None or rate is None:
                continue  # linha de cabeçalho ou vértice sem taxa divulgada
            points.append(
                CurvePoint(
                    maturity=maturity,
                    bond_type=row[CART_BOND_TYPE],
                    rate=rate,
                    price=cls._to_decimal(row[CART_PRICE]),
                    weight_pct=cls._to_decimal(row[CART_WEIGHT]),
                    duration_days=cls._to_int(row[CART_DURATION]),
                    business_days=cls._to_int(row[CART_BUSINESS_DAYS]),
                    selic_code=cls._clean(row[CART_SELIC_CODE]),
                    isin=cls._clean(row[CART_ISIN]),
                )
            )
        return sorted(points, key=lambda p: p.maturity)

    @classmethod
    def _first_index_row(cls, rows: list[list[str]], index: str) -> list[str]:
        for row in rows:
            if (
                row[0] == "2"
                and len(row) > CART_INDEX
                and cls._same_index(row[CART_INDEX], index)
            ):
                return row
        raise DataNotFoundError(f"Arquivo completo do IMA sem linhas para {index}")

    @staticmethod
    def _same_index(raw: str, index: str) -> bool:
        """Compara nomes de índice ignorando caixa e espaços ('IMA-B' != 'IMA-B 5')."""
        return raw.strip().upper() == index.upper()

    @staticmethod
    def _to_date(raw: str) -> date | None:
        try:
            return datetime.strptime(raw.strip(), "%d/%m/%Y").date()
        except ValueError:
            return None

    @staticmethod
    def _to_decimal(raw: str) -> Decimal | None:
        s = raw.strip().replace(".", "").replace(",", ".")
        if not s or s == NULL_MARKER:
            return None
        try:
            return Decimal(s)
        except InvalidOperation:
            return None

    @classmethod
    def _to_int(cls, raw: str) -> int | None:
        value = cls._to_decimal(raw)
        return int(value) if value is not None else None

    @staticmethod
    def _clean(raw: str) -> str | None:
        s = raw.strip()
        return None if not s or s == NULL_MARKER else s
