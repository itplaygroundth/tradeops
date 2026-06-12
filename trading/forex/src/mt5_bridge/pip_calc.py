"""
Pip Value Calculator — forex-specific position sizing helper.
Used by Risk Guardian to calculate lot size from risk amount.
"""
import logging
from typing import Callable, Optional

logger = logging.getLogger("pip_calc")

# Contract sizes per symbol (standard definitions)
CONTRACT_SIZES = {
    "XAUUSDm": 100,     # Gold: 1 lot = 100 ounces
    "XAGUSDm": 5000,    # Silver: 1 lot = 5000 ounces
}

# Pip sizes per symbol
PIP_SIZES = {
    "EURUSDm": 0.0001, "GBPUSDm": 0.0001, "AUDUSDm": 0.0001,
    "NZDUSDm": 0.0001, "USDCHFm": 0.0001, "USDCADm": 0.0001,
    "USDJPYm": 0.01,   "EURJPYm": 0.01,   "GBPJPYm": 0.01,
    "XAUUSDm": 0.1,    "XAGUSDm": 0.001,
}

def get_pip_size(symbol: str) -> float:
    return PIP_SIZES.get(symbol, 0.0001)

def get_contract_size(symbol: str) -> float:
    return CONTRACT_SIZES.get(symbol, 100000.0)  # Default 100,000 for standard FX pairs

def price_to_pips(symbol: str, price_distance: float) -> float:
    """Converts price distance to pips."""
    return price_distance / get_pip_size(symbol)

def pips_to_price(symbol: str, pips: float) -> float:
    """Converts pips to price distance."""
    return pips * get_pip_size(symbol)

def calculate_lot_size(
    account_balance: float,
    risk_pct: float,              # e.g., 0.01 = 1%
    sl_price_distance: float,
    symbol: str,
    get_price_func: Optional[Callable[[str], Optional[float]]] = None,
) -> float:
    """
    Calculates the lot size based on account balance, risk percentage, and SL distance.
    Uses universal quote-currency conversion to USD (the account base currency).
    """
    if sl_price_distance <= 0:
        return 0.01

    risk_amount = account_balance * risk_pct
    contract_size = get_contract_size(symbol)

    # 1. Parse base and quote currencies from the symbol
    # Most Forex pairs are 6 characters (e.g. EURUSD) or 6+ characters (e.g. EURUSDm)
    # Commodities like XAUUSD also end with USD
    quote_curr = "USD"
    if len(symbol) >= 6:
        quote_curr = symbol[3:6].upper()

    # 2. Determine conversion rate from Quote currency to USD
    quote_to_usd = 1.0
    if quote_curr != "USD":
        converted = False
        if get_price_func:
            # Try USD/Quote (e.g. USDJPY)
            usd_quote_pair = f"USD{quote_curr}"
            usd_quote_price = get_price_func(usd_quote_pair)
            if usd_quote_price:
                quote_to_usd = 1.0 / usd_quote_price
                converted = True
            else:
                # Try Quote/USD (e.g. GBPUSD)
                quote_usd_pair = f"{quote_curr}USD"
                quote_usd_price = get_price_func(quote_usd_pair)
                if quote_usd_price:
                    quote_to_usd = quote_usd_price
                    converted = True
        
        if not converted:
            # Fallbacks for major quote currencies if get_price_func is not available or fails
            fallbacks = {
                "JPY": 150.0,
                "CAD": 1.36,
                "CHF": 0.91,
                "GBP": 1.25,
                "EUR": 1.08,
            }
            fb_rate = fallbacks.get(quote_curr)
            if fb_rate:
                if quote_curr in ["JPY", "CAD", "CHF"]:
                    quote_to_usd = 1.0 / fb_rate
                else:
                    quote_to_usd = fb_rate
                logger.warning(f"Using fallback conversion rate for {quote_curr}: {quote_to_usd:.6f}")
            else:
                logger.warning(f"Could not convert quote currency {quote_curr} to USD. Using 1.0.")

    # 3. Calculate Risk in USD per 1 Lot traded
    # Risk in Quote currency = sl_price_distance * contract_size
    # Risk in USD = Risk in Quote * quote_to_usd
    risk_per_lot_usd = sl_price_distance * contract_size * quote_to_usd

    if risk_per_lot_usd <= 0:
        return 0.01

    lot_size = risk_amount / risk_per_lot_usd

    # Clamp: minimum 0.01 lots, maximum 10.0 lots
    clamped_lot = max(0.01, min(10.0, round(lot_size, 2)))
    return clamped_lot
