"""Provider ANBIMA — curvas da família IMA e mercado secundário de debêntures."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import pandas as pd

from brazilfi.core.cache import CACHE_ROOT, cached_download
from brazilfi.core.exceptions import DataNotFoundError
from brazilfi.core.http_client import HttpClient
from brazilfi.core.models import CurvePoint, YieldCurve

# Arquivo completo do IMA do último dia útil divulgado, linkado como "TXT" em
# https://www.anbima.com.br/informacoes/ima/ima.asp (seção "IMA arquivos completos").
# Traz TOTAIS (registro 1) e COMPOSIÇÃO DE CARTEIRA (registro 2) de toda a
# família IMA, delimitado por "@" e codificado em latin-1.
IMA_COMPLETO_TXT = "https://www.anbima.com.br/informacoes/ima/arqs/ima_completo.txt"

IMA_B = "IMA-B"
# Índices presentes no arquivo completo (bloco TOTAIS), conferidos no arquivo real.
IMA_INDICES = {
    "IMA-GERAL",
    "IMA-GERAL-EX-C",
    "IMA-B",
    "IMA-B 5",
    "IMA-B 5+",
    "IMA-S",
    "IRF-M",
    "IRF-M 1",
    "IRF-M 1+",
}

# Mercado secundário de debêntures: um TXT por dia útil, delimitado por "@", latin-1,
# linkado em https://www.anbima.com.br/informacoes/merc-sec-debentures/merc-sec-debentures.asp
DEBENTURES_URL = "https://www.anbima.com.br/informacoes/merc-sec-debentures/arqs/db{yymmdd}.txt"
CACHE_DIR = CACHE_ROOT / "anbima"
DEBENTURES_LOOKBACK_DAYS = 10
DEBENTURES_COLS = [
    "code",
    "issuer",
    "maturity",
    "index",
    "bid_rate",
    "ask_rate",
    "indicative_rate",
    "std_dev",
    "min_rate",
    "max_rate",
    "price",
    "pct_par",
    "duration",
    "pct_reune",
    "ntnb_reference",
]
DEBENTURES_NUMERIC = DEBENTURES_COLS[4:-1]  # ntnb_reference é a data da NTN-B de referência

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
        >>> an.curva_ima("IMA-B 5+")             # qualquer índice da família IMA
        >>> df = an.curva_ima_dataframe()        # mesmo, como DataFrame
        >>> an.debentures()                      # mercado secundário, último dia útil
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self.client = HttpClient(timeout=timeout, headers=BROWSER_HEADERS)

    # ---------- Curvas IMA ----------

    def curva_ima(self, index: str = IMA_B) -> YieldCurve:
        """
        Curva de juros de um índice da família IMA no último dia útil divulgado.

        Cada vértice é um título da carteira teórica do índice (NTN-B no IMA-B,
        LTN/NTN-F no IRF-M, LFT no IMA-S...), com a taxa indicativa ANBIMA
        (% a.a.), PU, peso e duration. Os agregados do índice (número-índice,
        variação diária, duration) vêm do bloco TOTAIS do mesmo arquivo.

        Args:
            index: "IMA-B" (default), "IMA-B 5", "IMA-B 5+", "IRF-M", "IRF-M 1",
                "IRF-M 1+", "IMA-S", "IMA-GERAL" ou "IMA-GERAL-EX-C".
        """
        index = index.strip().upper()
        if index not in IMA_INDICES:
            raise ValueError(f"index inválido. Use um de: {sorted(IMA_INDICES)}")

        rows = self._fetch_rows()
        points = self._parse_points(rows, index)
        if not points:
            raise DataNotFoundError(
                f"Arquivo completo do IMA sem composição de carteira para {index}"
            )

        totals = self._parse_totals(rows, index)
        reference_date = (
            self._to_date(totals[TOT_DATE])
            if totals
            else self._to_date(self._first_index_row(rows, index)[CART_DATE])
        )
        if reference_date is None:
            raise DataNotFoundError("Arquivo completo do IMA sem data de referência")

        return YieldCurve(
            index=index,
            reference_date=reference_date,
            source="anbima",
            index_number=self._to_decimal(totals[TOT_INDEX_NUMBER]) if totals else None,
            daily_change_pct=(
                self._to_decimal(totals[TOT_DAILY_CHANGE]) if totals else None
            ),
            duration_days=self._to_int(totals[TOT_DURATION]) if totals else None,
            points=points,
        )

    def curva_ima_dataframe(self, index: str = IMA_B) -> pd.DataFrame:
        """Mesmo que `curva_ima()`, mas como DataFrame indexado por vencimento."""
        return self.curva_ima(index).to_dataframe()

    # ---------- Debêntures ----------

    def debentures(self, on: str | date | None = None) -> pd.DataFrame:
        """
        Mercado secundário de debêntures: taxas indicativas ANBIMA de um dia útil.

        Uma linha por papel: código, emissor, vencimento, indexador (`index` cru
        e `indexer`/`coupon` separados, ex.: "DI + 1,6%" → "DI +" e 1.6), taxas
        de compra/venda/indicativa, PU, % do par, duration e NTN-B de referência.
        Taxas são % a.a.; "--"/"N/D" viram NaN.

        Sem `on`, recua dia a dia até o último arquivo publicado (o do dia sai no
        fim da tarde). Arquivos de dias passados ficam em cache permanente.
        """
        if on is not None:
            day = on if isinstance(on, date) else date.fromisoformat(on)
            return self._debentures_on(day)
        day = date.today()
        for _ in range(DEBENTURES_LOOKBACK_DAYS):
            try:
                return self._debentures_on(day)
            except DataNotFoundError:
                day -= timedelta(days=1)
        raise DataNotFoundError(
            f"Nenhum arquivo de debêntures publicado nos últimos {DEBENTURES_LOOKBACK_DAYS} dias"
        )

    def _debentures_on(self, day: date) -> pd.DataFrame:
        name = f"db{day:%y%m%d}.txt"
        path = cached_download(
            DEBENTURES_URL.format(yymmdd=f"{day:%y%m%d}"),
            CACHE_DIR / name,
            max_age_days=None,
            headers=BROWSER_HEADERS,
        )
        rows = [
            [f.strip() for f in line.split(DELIMITER)]
            for line in path.read_text(encoding=ENCODING).splitlines()
            if line.count(DELIMITER) >= len(DEBENTURES_COLS) - 1
        ]
        # rows[0] é o cabeçalho ("Código@Nome@...").
        records = [dict(zip(DEBENTURES_COLS, r, strict=False)) for r in rows[1:]]
        if not records:
            raise DataNotFoundError(f"Arquivo de debêntures de {day:%d/%m/%Y} veio vazio")

        df = pd.DataFrame(records)
        df.insert(0, "date", pd.Timestamp(day))
        for col in ("maturity", "ntnb_reference"):
            df[col] = pd.to_datetime(df[col], format="%d/%m/%Y", errors="coerce")
        for col in DEBENTURES_NUMERIC:
            df[col] = df[col].map(self._to_float)
        split = df["index"].map(self._split_index)
        df["indexer"] = [s[0] for s in split]
        df["coupon"] = [s[1] for s in split]
        return df.sort_values("code").reset_index(drop=True)

    @classmethod
    def _to_float(cls, raw: str) -> float:
        value = cls._to_decimal(raw)
        return float(value) if value is not None else float("nan")

    @classmethod
    def _split_index(cls, raw: str) -> tuple[str, float]:
        """'DI + 1,6%' → ('DI +', 1.6); '100% do DI' → ('% DI', 100.0); sem número → NaN."""
        m = re.match(r"^([\d.,]+)% do (.+)$", raw)
        if m:
            return f"% {m.group(2).strip()}", cls._to_float(m.group(1))
        m = re.match(r"^(.*?)\s*([\d.,]+)%$", raw)
        if m:
            return m.group(1).strip(), cls._to_float(m.group(2))
        return raw, float("nan")

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
        if not s or s in (NULL_MARKER, "N/D"):
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
