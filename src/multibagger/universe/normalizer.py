"""Symbol normalization and canonicalization utilities"""

import logging
import re

logger = logging.getLogger(__name__)


class SymbolNormalizer:
    """Handles symbol normalization and canonicalization"""

    # Common symbol transformations
    SYMBOL_REPLACEMENTS = {
        ".": "-",  # BRK.B -> BRK-B
        "/": "-",  # Some symbols use slashes
        "^": "-",  # Caret symbols
    }

    # Preferred exchange suffixes for different markets
    EXCHANGE_SUFFIXES = {
        "US": "",  # US symbols don't need suffix
        "INDIA": ".NS",  # NSE suffix
        "CANADA": ".TO",  # Toronto
        "UK": ".L",  # London
        "GERMANY": ".DE",  # Xetra
    }

    # Known symbol corrections
    SYMBOL_CORRECTIONS = {
        # Common misspellings or variations
        "BRKB": "BRK-B",  # Berkshire Hathaway Class B
        "BRKA": "BRK-A",  # Berkshire Hathaway Class A
        "RDS/A": "RDS-A",  # Royal Dutch Shell
        "RDS/B": "RDS-B",
        "FWONA": "FWON-A",  # Liberty Media
        "FWONK": "FWON-K",
        "LBRDA": "LBRD-A",
        "LBRDK": "LBRD-K",
        "NWS/A": "NWSA",  # News Corp Class A
        "NWS/B": "NWS",
    }

    # Symbols that should not have exchange suffixes
    NO_SUFFIX_SYMBOLS = {
        # US market symbols that are globally recognized
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "TSLA",
        "META",
        "NVDA",
        "NFLX",
        "JPM",
        "BAC",
        "WFC",
        "C",
        "GS",
        "MS",
        "BLK",
        "AXP",
        "V",
        "MA",
        "JNJ",
        "PFE",
        "MRK",
        "ABT",
        "TMO",
        "DHR",
        "LLY",
        "UNH",
        "CVS",
        "WMT",
        "HD",
        "MCD",
        "KO",
        "PEP",
        "COST",
        "WBA",
        "CL",
        "KMB",
        "PG",
        "EL",
        "CLX",
        "KHC",
        "MNST",
        "STZ",
        "SYY",
        "GIS",
        "HSY",
        "XOM",
        "CVX",
        "COP",
        "EOG",
        "PXD",
        "OXY",
        "SLB",
        "HAL",
        "BKR",
        "CAT",
        "DE",
        "EMR",
        "ETN",
        "GE",
        "HON",
        "MMM",
        "ROP",
        "ROK",
        "CMI",
        "DOV",
        "FLS",
        "FTV",
        "ITW",
        "IR",
        "PH",
        "PNR",
        "SWK",
        "NEM",
        "FCX",
        "APD",
        "DD",
        "DOW",
        "ECL",
        "IFF",
        "LIN",
        "LYB",
        "MLM",
        "PPG",
        "SHW",
        "VMC",
        "VZ",
        "T",
        "TMUS",
        "LUMN",
        "IPG",
        "NWSA",
        "OMC",
        "EA",
        "TTWO",
        "ATVI",
        "AMD",
        "INTC",
        "QCOM",
        "TXN",
        "ADI",
        "MCHP",
        "XLNX",
        "AVGO",
        "NXPI",
        "SWKS",
        "QRVO",
        "LRCX",
        "KLAC",
        "AMAT",
        "ASML",
        "TSM",
        "UMC",
        "SPOT",
        "PYPL",
        "SQ",
        "SHOP",
        "UBER",
        "LYFT",
        "ZM",
        "CRWD",
        "ZS",
        "OKTA",
        "DDOG",
        "NET",
        "FSLY",
        "PINS",
        "SNAP",
        "TWTR",
        "FB",
        "TWLO",
        "DIS",
        "CMCSA",
        "CHTR",
        "FOXA",
        "FOX",
        "SIRI",
        "VIAC",
        "LBRD-A",
        "LBRD-K",
        "FWON-A",
        "FWON-K",
        "BRK-A",
        "BRK-B",
        "RDS-A",
        "RDS-B",
        "TWO",
        "THREE",
        "FOUR",
        "FIVE",
        "SIX",
        "SEVEN",
        "EIGHT",
        "NINE",
        "TEN",
        "ELEVEN",
        "TWELVE",
        "THIRTEEN",
        "FOURTEEN",
        "FIFTEEN",
        "SIXTEEN",
        "SEVENTEEN",
        "EIGHTEEN",
        "NINETEEN",
        "TWENTY",
    }

    def __init__(self):
        self._compiled_patterns = self._compile_patterns()

    def _compile_patterns(self) -> dict[str, re.Pattern]:
        """Compile regex patterns for symbol validation"""
        return {
            "valid_symbol": re.compile(r"^[A-Z0-9\-/\.\^]{1,10}$"),
            "exchange_suffix": re.compile(r"\.(NS|TO|L|DE|HK|SS|SZ)$"),
            "class_suffix": re.compile(r"[-/](A|B|C|K)$"),
        }

    def normalize_symbol(self, symbol: str, exchange_code: str = "US") -> str:
        """Normalize a symbol to canonical form"""
        if not symbol:
            return ""

        # Convert to uppercase
        symbol = symbol.upper().strip()

        # Apply known corrections first
        symbol = self.SYMBOL_CORRECTIONS.get(symbol, symbol)

        # Replace special characters
        for old, new in self.SYMBOL_REPLACEMENTS.items():
            symbol = symbol.replace(old, new)

        # Remove any existing exchange suffixes for US symbols
        if exchange_code == "US":
            symbol = self._remove_exchange_suffix(symbol)

        # Add appropriate exchange suffix for non-US markets
        if exchange_code != "US" and symbol not in self.NO_SUFFIX_SYMBOLS:
            suffix = self.EXCHANGE_SUFFIXES.get(exchange_code, "")
            if suffix and not symbol.endswith(suffix):
                symbol = f"{symbol}{suffix}"

        # Validate final symbol
        if not self._is_valid_symbol(symbol):
            logger.warning(f"Invalid symbol format: {symbol}")
            return ""

        return symbol

    def _remove_exchange_suffix(self, symbol: str) -> str:
        """Remove exchange suffix from symbol"""
        match = self._compiled_patterns["exchange_suffix"].search(symbol)
        if match:
            return symbol[: match.start()]
        return symbol

    def _is_valid_symbol(self, symbol: str) -> bool:
        """Check if symbol format is valid"""
        return bool(self._compiled_patterns["valid_symbol"].match(symbol))

    def extract_base_symbol(self, symbol: str) -> str:
        """Extract base symbol without class or exchange suffixes"""
        # Remove exchange suffix
        symbol = self._remove_exchange_suffix(symbol)

        # Remove class suffix
        match = self._compiled_patterns["class_suffix"].search(symbol)
        if match:
            symbol = symbol[: match.start()]

        return symbol

    def get_symbol_class(self, symbol: str) -> str | None:
        """Extract class suffix (A, B, etc.) from symbol"""
        match = self._compiled_patterns["class_suffix"].search(symbol)
        if match:
            return match.group(1)
        return None

    def is_preferred_symbol(self, symbol: str, exchange_code: str) -> bool:
        """Check if symbol follows preferred format for exchange"""
        normalized = self.normalize_symbol(symbol, exchange_code)
        return normalized == symbol

    def deduplicate_symbols(self, symbols: list) -> list:
        """Remove duplicate symbols, preferring canonical forms"""
        seen_bases = set()
        unique_symbols = []

        # Sort by preference (canonical forms first)
        sorted_symbols = sorted(
            symbols,
            key=lambda s: (
                not self._is_valid_symbol(s),  # Invalid symbols last
                len(s),  # Shorter symbols preferred
                s,  # Alphabetical fallback
            ),
        )

        for symbol in sorted_symbols:
            base = self.extract_base_symbol(symbol)
            if base not in seen_bases:
                seen_bases.add(base)
                unique_symbols.append(symbol)

        return unique_symbols

    def normalize_universe_entry(self, entry: "UniverseEntry") -> "UniverseEntry":
        """Normalize a universe entry's symbol"""
        from .adapters import UniverseEntry  # Import here to avoid circular import

        normalized_symbol = self.normalize_symbol(entry.symbol, entry.exchange_code)

        if normalized_symbol != entry.symbol:
            logger.debug(f"Normalized {entry.symbol} -> {normalized_symbol}")

        return UniverseEntry(
            symbol=normalized_symbol,
            name=entry.name,
            exchange_code=entry.exchange_code,
            market_cap=entry.market_cap,
            sector=entry.sector,
            industry=entry.industry,
            is_active=entry.is_active,
            is_etf=entry.is_etf,
            is_adr=entry.is_adr,
            is_common_equity=entry.is_common_equity,
            raw_data=entry.raw_data,
        )
