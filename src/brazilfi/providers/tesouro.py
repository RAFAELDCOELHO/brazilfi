"""Provider Tesouro Direto — títulos disponíveis + histórico."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import httpx
import pandas as pd

from brazilfi.core.exceptions import DataNotFoundError, ProviderError
from brazilfi.core.http_client import HttpClient
from brazilfi.core.models import Bond

# CSV histórico oficial (Tesouro Transparente, dados abertos). O endpoint JSON
# ao-vivo do tesourodireto.com.br fica atrás de Cloudflare e não é usado.
HISTORICO_URL = (
    "https://www.tesourotransparente.gov.br/ckan/dataset/"
    "df56aa42-484a-4a59-8184-7676580c81e3/resource/"
    "796d2059-14e9-44e3-80c9-2d9e30b405c1/download/PrecoTaxaTesouroDireto.csv"
)

CACHE_DIR = Path.home() / ".cache" / "brazilfi"
CACHE_FILE = CACHE_DIR / "tesouro_historico.csv"
CACHE_MAX_AGE_DAYS = 1  # recarrega se tiver mais de 1 dia

# O gov.br rejeita alguns User-Agents genéricos.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/csv, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


class TesouroDireto:
    """
    Wrapper para Tesouro Direto.

    Exemplos:
        >>> td = TesouroDireto()
        >>> bonds = td.available()              # títulos à venda agora
        >>> df = td.available_dataframe()       # mesmo, como DataFrame
        >>> hist = td.history("Tesouro IPCA+", maturity=2029)
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self.client = HttpClient(timeout=timeout, headers=BROWSER_HEADERS)

    # ---------- Disponíveis ----------

    def available(self) -> list[Bond]:
        """
        Títulos do Tesouro Direto disponíveis (baseado no último pregão).

        Usa o CSV oficial do Tesouro Transparente (gov.br, dados abertos).
        Dados são do último dia útil (D-1), não ao vivo.

        Os endpoints ao-vivo do tesourodireto.com.br estão atrás de Cloudflare
        e não são acessíveis via script Python. Esta fonte (gov.br) é mais
        robusta e oficial.
        """
        df = self._load_historico()
        latest_date = df["date"].max()
        active = df[(df["date"] == latest_date) & (df["maturity"] > latest_date)].copy()

        if active.empty:
            raise DataNotFoundError("Nenhum título ativo no último pregão do CSV")

        bonds: list[Bond] = []
        for _, row in active.iterrows():
            try:
                bond_type_raw = str(row["bond_type"]).strip()
                name = self._make_name(bond_type_raw, row["maturity"])
                bonds.append(Bond(
                    name=name,
                    bond_type=self._normalize_type(bond_type_raw),
                    maturity=row["maturity"].date(),
                    index=self._infer_index(name),
                    buy_rate=self._to_decimal(row.get("buy_rate")),
                    sell_rate=self._to_decimal(row.get("sell_rate")),
                    buy_price=self._to_decimal(row.get("buy_price")),
                    sell_price=self._to_decimal(row.get("sell_price")),
                    min_investment=None,
                    isin=None,
                    available=True,
                ))
            except (KeyError, ValueError, TypeError, AttributeError):
                continue
        return bonds

    @staticmethod
    def _make_name(bond_type: str, maturity: Any) -> str:
        """Constrói nome comercial a partir do tipo + ano de vencimento."""
        year = maturity.year if hasattr(maturity, "year") else int(str(maturity)[:4])
        t = bond_type.lower()
        if "ipca" in t and "principal" in t:
            return f"Tesouro IPCA+ {year}"
        if "ipca" in t:
            return f"Tesouro IPCA+ com Juros Semestrais {year}"
        if "prefixado" in t and "juros" in t:
            return f"Tesouro Prefixado com Juros Semestrais {year}"
        if "prefixado" in t:
            return f"Tesouro Prefixado {year}"
        if "selic" in t:
            return f"Tesouro Selic {year}"
        return f"{bond_type} {year}"

    @staticmethod
    def _normalize_type(raw: str) -> str:
        """Normaliza tipo do CSV para código tradicional."""
        r = raw.lower()
        if "prefixado" in r and "juros" in r:
            return "NTN-F"
        if "prefixado" in r:
            return "LTN"
        if "ipca" in r and "principal" in r:
            return "NTN-B Principal"
        if "ipca" in r or "renda+" in r or "educa+" in r:
            return "NTN-B"
        if "igpm" in r or "igp-m" in r:
            return "NTN-C"
        if "selic" in r:
            return "LFT"
        return "Desconhecido"

    @staticmethod
    def _to_decimal(val: Any) -> Decimal | None:
        if val is None or pd.isna(val):
            return None
        try:
            return Decimal(str(val))
        except Exception:
            return None

    def available_dataframe(self) -> pd.DataFrame:
        """Mesmo que `available()`, mas como DataFrame pronto para análise."""
        bonds = self.available()
        if not bonds:
            return pd.DataFrame()
        rows = [b.model_dump() for b in bonds]
        return pd.DataFrame(rows)

    # ---------- Histórico ----------

    def history(
        self,
        bond_type: str | None = None,
        maturity: int | date | None = None,
        start: str | date | None = None,
        end: str | date | None = None,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        """
        Histórico de preços e taxas.

        Args:
            bond_type: filtra por tipo (ex: "Tesouro IPCA+", "Tesouro Prefixado").
                       Use contains matching (case-insensitive).
            maturity: ano (int) ou data (date) de vencimento para filtrar.
            start/end: range de datas (string "YYYY-MM-DD" ou date).
            force_refresh: ignora cache e rebaixa o CSV.
        """
        df = self._load_historico(force_refresh=force_refresh)

        if bond_type:
            df = df[df["bond_type"].str.contains(bond_type, case=False, na=False)]
        if maturity is not None:
            if isinstance(maturity, int):
                df = df[df["maturity"].dt.year == maturity]
            else:
                df = df[df["maturity"] == pd.Timestamp(maturity)]
        if start:
            df = df[df["date"] >= pd.Timestamp(start)]
        if end:
            df = df[df["date"] <= pd.Timestamp(end)]

        if df.empty:
            raise DataNotFoundError(
                f"Sem histórico para filtros: type={bond_type} mat={maturity}"
            )
        return df.sort_values("date").reset_index(drop=True)

    def latest_from_history(self) -> pd.DataFrame:
        """Fallback para quando available() falha (bloqueio Cloudflare)."""
        df = self._load_historico()
        latest_date = df["date"].max()
        latest = df[df["date"] == latest_date].copy()
        latest = latest[latest["maturity"] > latest_date]
        sorted_df = latest.sort_values(["bond_type", "maturity"]).reset_index(drop=True)
        return cast("pd.DataFrame", sorted_df)

    def clear_cache(self) -> None:
        """Remove o cache local do CSV."""
        CACHE_FILE.unlink(missing_ok=True)

    # ---------- Internals ----------

    def _load_historico(self, force_refresh: bool = False) -> pd.DataFrame:
        """Baixa (ou usa cache) do CSV histórico do Tesouro Transparente."""
        if force_refresh or self._cache_stale():
            self._download_historico()
        if not CACHE_FILE.exists():
            raise ProviderError("Não foi possível obter o CSV do Tesouro Transparente")

        df = pd.read_csv(CACHE_FILE, sep=";", decimal=",", encoding="utf-8")
        return self._normalize_historico(df)

    @staticmethod
    def _cache_stale() -> bool:
        if not CACHE_FILE.exists():
            return True
        age = datetime.now().timestamp() - CACHE_FILE.stat().st_mtime
        return age > (CACHE_MAX_AGE_DAYS * 24 * 3600)

    def _download_historico(self) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        # Stream pra não estourar memória (CSV ~100MB)
        tmp = CACHE_FILE.with_suffix(".csv.part")
        with httpx.stream(
            "GET",
            HISTORICO_URL,
            timeout=120.0,
            headers=BROWSER_HEADERS,
            follow_redirects=True,
        ) as resp:
            if resp.status_code >= 400:
                raise ProviderError(
                    f"Falha ao baixar histórico Tesouro: HTTP {resp.status_code}"
                )
            with tmp.open("wb") as f:
                for chunk in resp.iter_bytes():
                    f.write(chunk)
        # Só substitui o cache depois do download completo: um Ctrl+C no meio
        # não deixa um CSV truncado "fresco" por 24h.
        tmp.replace(CACHE_FILE)

    @staticmethod
    def _normalize_historico(df: pd.DataFrame) -> pd.DataFrame:
        """Renomeia colunas do CSV bruto para nomes em inglês/snake_case."""
        rename = {
            "Tipo Titulo": "bond_type",
            "Data Vencimento": "maturity",
            "Data Base": "date",
            "Taxa Compra Manha": "buy_rate",
            "Taxa Venda Manha": "sell_rate",
            "PU Compra Manha": "buy_price",
            "PU Venda Manha": "sell_price",
            "PU Base Manha": "base_price",
        }
        df = df.rename(columns=rename)
        # Parse datas (formato brasileiro DD/MM/YYYY)
        for col in ("date", "maturity"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], format="%d/%m/%Y", errors="coerce")
        return df

    @staticmethod
    def _infer_index(name: str) -> str | None:
        n = name.lower()
        if "ipca" in n or "renda+" in n or "educa+" in n:
            return "IPCA"
        if "igpm" in n or "igp-m" in n:
            return "IGP-M"
        if "selic" in n:
            return "SELIC"
        if "prefixado" in n:
            return "Prefixado"
        return None
