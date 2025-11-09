"""Eligibility checking and filtering for universe entries"""

import logging
from dataclasses import dataclass

from multibagger.config import Config

logger = logging.getLogger(__name__)


@dataclass
class EligibilityFlags:
    """Eligibility flags for a security"""

    active: bool = True
    common_equity: bool = True
    etf: bool = False
    adr: bool = False
    penny_stock: bool = False
    has_liquidity: bool = True
    meets_size_criteria: bool = True
    meets_price_criteria: bool = True

    def is_eligible(self, config: Config) -> bool:
        """Check if security meets all eligibility criteria"""
        # Must be active
        if not self.active:
            return False

        # Must be common equity (unless ETFs are allowed)
        if not self.common_equity and not config.universe.get("include_etfs", False):
            return False

        # Exclude penny stocks
        if self.penny_stock and not config.universe.get("include_penny_stocks", False):
            return False

        # Must have liquidity
        if not self.has_liquidity:
            return False

        # Must meet size criteria
        if not self.meets_size_criteria:
            return False

        # Must meet price criteria
        if not self.meets_price_criteria:
            return False

        return True


class EligibilityChecker:
    """Checks eligibility of securities based on configuration"""

    def __init__(self, config: Config):
        self.config = config
        self._min_market_cap = config.universe.get("min_market_cap", 100_000_000)
        self._min_price = config.universe.get("min_price", 5.00)
        self._min_volume = config.universe.get("min_daily_volume", 100_000)
        self._exclude_otc = config.universe.get("exclude_otc", True)
        self._exclude_adrs = config.universe.get("exclude_adrs", True)

    def check_eligibility(self, entry: "UniverseEntry") -> EligibilityFlags:
        """Check eligibility flags for a universe entry"""

        flags = EligibilityFlags()

        # Active status
        flags.active = entry.is_active

        # Security type flags
        flags.etf = entry.is_etf
        flags.adr = entry.is_adr
        flags.common_equity = entry.is_common_equity

        # Penny stock check (price < $5)
        flags.penny_stock = self._is_penny_stock(entry)

        # Liquidity check (this would need volume data, placeholder for now)
        flags.has_liquidity = self._has_liquidity(entry)

        # Size criteria (market cap)
        flags.meets_size_criteria = self._meets_size_criteria(entry)

        # Price criteria
        flags.meets_price_criteria = self._meets_price_criteria(entry)

        return flags

    def _is_penny_stock(self, entry: "UniverseEntry") -> bool:
        """Check if security is a penny stock based on price"""
        # This is a simplified check - in reality would need current price data
        # For now, we'll assume non-penny unless we have explicit data
        return False  # Placeholder

    def _has_liquidity(self, entry: "UniverseEntry") -> bool:
        """Check if security has sufficient liquidity"""
        # This would check average daily volume
        # For now, assume liquid unless OTC or very small cap
        if self._exclude_otc and entry.exchange_code in ["OTC", "PINK"]:
            return False

        # Small caps might be less liquid
        if entry.market_cap and entry.market_cap < self._min_market_cap * 0.1:
            return False

        return True

    def _meets_size_criteria(self, entry: "UniverseEntry") -> bool:
        """Check if security meets market cap requirements"""
        if entry.market_cap is None:
            # If no market cap data, assume it meets criteria for now
            # In production, might want to fetch this data
            return True

        return entry.market_cap >= self._min_market_cap

    def _meets_price_criteria(self, entry: "UniverseEntry") -> bool:
        """Check if security meets price requirements"""
        # This would need current price data
        # For now, assume meets criteria
        return True

    def filter_eligible(self, entries: list["UniverseEntry"]) -> list["UniverseEntry"]:
        """Filter list of entries to only eligible ones"""
        eligible = []

        for entry in entries:
            flags = self.check_eligibility(entry)
            if flags.is_eligible(self.config):
                eligible.append(entry)
            else:
                logger.debug(
                    f"Filtered out {entry.symbol}: {self._get_filter_reason(flags)}"
                )

        logger.info(f"Eligibility filter: {len(entries)} -> {len(eligible)} entries")
        return eligible

    def _get_filter_reason(self, flags: EligibilityFlags) -> str:
        """Get reason why entry was filtered out"""
        reasons = []

        if not flags.active:
            reasons.append("inactive")
        if not flags.common_equity and not flags.etf:
            reasons.append("not equity/ETF")
        if flags.penny_stock:
            reasons.append("penny stock")
        if not flags.has_liquidity:
            reasons.append("low liquidity")
        if not flags.meets_size_criteria:
            reasons.append("small cap")
        if not flags.meets_price_criteria:
            reasons.append("low price")

        return ", ".join(reasons) if reasons else "unknown"

    def get_eligibility_stats(self, entries: list["UniverseEntry"]) -> dict[str, int]:
        """Get statistics on eligibility filtering"""
        total = len(entries)
        eligible = 0
        reasons = {}

        for entry in entries:
            flags = self.check_eligibility(entry)
            if flags.is_eligible(self.config):
                eligible += 1
            else:
                reason = self._get_filter_reason(flags)
                reasons[reason] = reasons.get(reason, 0) + 1

        return {
            "total_entries": total,
            "eligible_entries": eligible,
            "filtered_entries": total - eligible,
            "filter_reasons": reasons,
        }
