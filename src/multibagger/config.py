"""Configuration loading and management for Multi-Bagger Research System"""

from pathlib import Path
from typing import Any

import yaml

from .data.config import DataConfig


class Config:
    """Main configuration class that loads and provides access to all settings"""

    def __init__(self, config_path: str | None = None):
        self.config_path = Path(config_path) if config_path else Path("config.yml")
        self._config: dict[str, Any] = {}
        self._data_config: DataConfig | None = None

        self.load_config()

    def load_config(self) -> None:
        """Load configuration from YAML file"""
        if self.config_path.exists():
            with open(self.config_path) as f:
                self._config = yaml.safe_load(f) or {}
        else:
            # Use defaults if config file doesn't exist
            self._config = self._get_defaults()

    def _get_defaults(self) -> dict[str, Any]:
        """Get default configuration values"""
        return {
            "markets": ["US"],
            "universe": {
                "size_target": 5000,
                "min_market_cap": 100_000_000,
                "min_price": 5.00,
                "exclude_otc": True,
                "exclude_adrs": True,
            },
            "data_sources": {
                "primary": "YAHOO",
                "backup": "ALPHA_VANTAGE",
            },
            "rate_limits": {
                "yahoo": 2000,
                "alpha_vantage": 5,
            },
            "data": {
                "sources": {
                    "yahoo": {
                        "enabled": True,
                        "rate_limit_per_minute": 2000,
                        "user_agent": "MultiBagger/1.0",
                        "timeout_seconds": 30,
                    },
                    "alpha_vantage": {
                        "enabled": False,
                        "rate_limit_per_minute": 5,
                        "timeout_seconds": 30,
                    },
                },
            },
        }

    @property
    def markets(self) -> list[str]:
        """Get enabled markets"""
        return self._config.get("markets", ["US"])

    @property
    def universe(self) -> dict[str, Any]:
        """Get universe configuration"""
        return self._config.get("universe", {})

    @property
    def data_sources(self) -> dict[str, Any]:
        """Get data sources configuration"""
        return self._config.get("data_sources", {})

    @property
    def rate_limits(self) -> dict[str, Any]:
        """Get rate limits configuration"""
        return self._config.get("rate_limits", {})

    @property
    def data(self) -> dict[str, Any]:
        """Get data layer configuration"""
        return self._config.get("data", {})

    @property
    def execution(self) -> dict[str, Any]:
        """Get execution configuration"""
        return self._config.get("execution", {})

    @property
    def dev(self) -> dict[str, Any]:
        """Get development configuration"""
        return self._config.get("dev", {})

    def get_data_config(self) -> DataConfig:
        """Get DataConfig instance for data layer"""
        if self._data_config is None:
            self._data_config = DataConfig.from_config(self._config)
        return self._data_config

    def reload(self) -> None:
        """Reload configuration from file"""
        self._config = {}
        self._data_config = None
        self.load_config()

    def __getitem__(self, key: str) -> Any:
        """Allow dictionary-like access"""
        return self._config[key]

    def __contains__(self, key: str) -> bool:
        """Allow 'in' operator"""
        return key in self._config

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with default"""
        return self._config.get(key, default)


# Global config instance
_config_instance: Config | None = None


def get_config(config_path: str | None = None) -> Config:
    """Get global configuration instance"""
    global _config_instance
    if _config_instance is None or config_path:
        _config_instance = Config(config_path)
    return _config_instance


def reload_config() -> None:
    """Reload global configuration"""
    global _config_instance
    if _config_instance:
        _config_instance.reload()
