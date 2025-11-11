"""Data layer configuration"""

from dataclasses import dataclass
from typing import Any


@dataclass
class SourceConfig:
    """Configuration for a single data source"""

    enabled: bool = True
    rate_limit_per_minute: int = 60
    timeout_seconds: int = 30
    api_key: str | None = None
    base_url: str | None = None


@dataclass
class CacheConfig:
    """Cache configuration"""

    enabled: bool = True
    ttl_prices: int = 1  # days
    ttl_fundamentals: int = 90  # days
    ttl_instruments: int = 30  # days
    ttl_filings: int = 365  # days


@dataclass
class DataConfig:
    """Main data layer configuration"""

    sources: dict[str, SourceConfig]
    cache: CacheConfig
    cache_only_mode: bool = False
    batch_size: int = 50
    max_workers: int = 4

    @classmethod
    def create_default(cls) -> "DataConfig":
        """Create default configuration"""
        return cls(
            sources={
                "yahoo": SourceConfig(
                    enabled=True,
                    rate_limit_per_minute=2000,
                    timeout_seconds=30,
                ),
                "alpha_vantage": SourceConfig(
                    enabled=False,
                    rate_limit_per_minute=5,
                    timeout_seconds=30,
                ),
            },
            cache=CacheConfig(),
        )

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "DataConfig":
        """Create from configuration dictionary"""
        data_config = config.get("data", {})
        sources_config = data_config.get("sources", {})

        # Parse source configs
        sources = {}
        for name, src_cfg in sources_config.items():
            sources[name] = SourceConfig(
                enabled=src_cfg.get("enabled", True),
                rate_limit_per_minute=src_cfg.get("rate_limit_per_minute", 60),
                timeout_seconds=src_cfg.get("timeout_seconds", 30),
                api_key=src_cfg.get("api_key"),
                base_url=src_cfg.get("base_url"),
            )

        # Parse cache config
        cache_config = data_config.get("cache", {})
        cache = CacheConfig(
            enabled=cache_config.get("enabled", True),
            ttl_prices=cache_config.get("ttl_prices", 1),
            ttl_fundamentals=cache_config.get("ttl_fundamentals", 90),
            ttl_instruments=cache_config.get("ttl_instruments", 30),
            ttl_filings=cache_config.get("ttl_filings", 365),
        )

        return cls(
            sources=sources,
            cache=cache,
            cache_only_mode=data_config.get("cache_only_mode", False),
            batch_size=data_config.get("batch_size", 50),
            max_workers=data_config.get("max_workers", 4),
        )
