"""Hierarquia de exceções da biblioteca."""


class BrazilFiError(Exception):
    """Base para todas as exceções da biblioteca."""


class ProviderError(BrazilFiError):
    """Erro ao acessar um provider (API externa)."""


class RateLimitError(ProviderError):
    """API respondeu com rate limit excedido."""


class DataNotFoundError(ProviderError):
    """Série/ticker/recurso não encontrado na API."""
