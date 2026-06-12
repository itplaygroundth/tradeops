"""
Pip Value Calculator — forex-specific position sizing helper.
Used by Risk Guardian to calculate lot size from risk amount.

Cent-account support
--------------------
On a cent (USC) account the broker reports balance/equity in *cents*:
1 USC = 0.01 USD, so a "$5" deposit shows as 500. The contract size and
pip value are still quoted in USD, so to size positions correctly we must
convert the cent balance back to USD (divide by 100) before applying the
risk percentage. Detection is automatic via account currency == "USC";
the divisor can be overridden with CENT_ACCOUNT_DIVISOR.
"""
import logging
import os
from typing import Callable, Optional

logger = logging.getLogger("pip_calc")

# Cent-account currency codes (Exness uses "USC"). Override with
# CENT_CURRENCIES env (comma-separated) if your broker differs.
CENT_CURRENCIES = {
    c.strip().upper()
    for c in os.getenv("CENT_CURRENCIES", "USC,EUC").split(",")
    if c.strip()
}
# 1 USC = 0.01 USD → divide cent balance by 100 to get USD.
CENT_ACCOUNT_DIVISOR = float(os.getenv("CENT_ACCOUNT_DIVISOR", "100"))

def is_cent_currency(currency: Optional[str]) -> bool:
    return bool(currency) and currency.strip().upper() in CENT_CURRENCIES

# Contract sizes per symbol (standard definitions).
# Override per-symbol via CONTRACT_SIZE_<SYMBOL> env, e.g.
# CONTRACT_SIZE_EURUSDM=1000 for a broker whose lot is micro-sized.
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
    # Support symbols with or without 'm' suffix and case-insensitive
    if symbol in PIP_SIZES:
        return PIP_SIZES[symbol]
    sym_up = symbol.upper()
    if sym_up in PIP_SIZES:
        return PIP_SIZES[sym_up]
    if sym_up + "m" in PIP_SIZES:
        return PIP_SIZES[sym_up + "m"]
    if sym_up.endswith("M") and sym_up[:-1] in PIP_SIZES:
        return PIP_SIZES[sym_up[:-1]]
    return 0.0001

def get_contract_size(symbol: str) -> float:
    # Per-symbol env override (highest priority): CONTRACT_SIZE_EURUSDM=1000
    env_override = os.getenv(f"CONTRACT_SIZE_{symbol.upper()}")
    if env_override:
        try:
            return float(env_override)
        except ValueError:
            logger.warning(f"Invalid CONTRACT_SIZE_{symbol.upper()}={env_override!r}; ignoring")
    # Support symbols with or without 'm' suffix and case-insensitive
    if symbol in CONTRACT_SIZES:
        return CONTRACT_SIZES[symbol]
    sym_up = symbol.upper()
    if sym_up in CONTRACT_SIZES:
        return CONTRACT_SIZES[sym_up]
    if sym_up + "m" in CONTRACT_SIZES:
        return CONTRACT_SIZES[sym_up + "m"]
    if sym_up.endswith("M") and sym_up[:-1] in CONTRACT_SIZES:
        return CONTRACT_SIZES[sym_up[:-1]]
    return 100000.0  # Default 100,000 for standard FX pairs

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
    account_currency: Optional[str] = None,
) -> float:
    """
    Calculates the lot size based on account balance, risk percentage, and SL distance.
    Uses universal quote-currency conversion to USD (the account base currency).

    On a cent account (account_currency == "USC"), the balance is in cents;
    it is converted to USD (÷ CENT_ACCOUNT_DIVISOR) so the USD-denominated
    pip value sizes the position correctly.
    """
    if sl_price_distance <= 0:
        return 0.01

    # Convert cent-account balance to USD before applying risk %.
    if is_cent_currency(account_currency):
        account_balance = account_balance / CENT_ACCOUNT_DIVISOR

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


def calculate_lot_size_for_profit_target(
    target_profit_usd: float,
    tp_price_distance: float,
    symbol: str,
    get_price_func: Optional[Callable[[str], Optional[float]]] = None,
    account_currency: Optional[str] = None,
) -> float:
    """Return lot size that would make roughly target_profit_usd at TP.

    The returned lot is expressed in broker lots and rounded/clamped to the
    platform's broad 0.01..10.0 range. target_profit_usd is always treated as
    USD-equivalent, including cent accounts, because contract value and pip
    value calculations are USD-denominated.
    """
    if target_profit_usd <= 0 or tp_price_distance <= 0:
        return 0.01

    target_profit = float(target_profit_usd)

    contract_size = get_contract_size(symbol)
    quote_curr = "USD"
    if len(symbol) >= 6:
        quote_curr = symbol[3:6].upper()

    quote_to_usd = 1.0
    if quote_curr != "USD":
        converted = False
        if get_price_func:
            usd_quote_pair = f"USD{quote_curr}"
            usd_quote_price = get_price_func(usd_quote_pair)
            if usd_quote_price:
                quote_to_usd = 1.0 / usd_quote_price
                converted = True
            else:
                quote_usd_pair = f"{quote_curr}USD"
                quote_usd_price = get_price_func(quote_usd_pair)
                if quote_usd_price:
                    quote_to_usd = quote_usd_price
                    converted = True
        if not converted:
            fallbacks = {
                "JPY": 150.0,
                "CAD": 1.36,
                "CHF": 0.91,
                "GBP": 1.25,
                "EUR": 1.08,
            }
            fb_rate = fallbacks.get(quote_curr)
            if fb_rate:
                quote_to_usd = 1.0 / fb_rate if quote_curr in ["JPY", "CAD", "CHF"] else fb_rate
            else:
                logger.warning(f"Could not convert quote currency {quote_curr} to USD. Using 1.0.")

    profit_per_lot = tp_price_distance * contract_size * quote_to_usd
    if profit_per_lot <= 0:
        return 0.01

    lot_size = target_profit / profit_per_lot
    return max(0.01, min(10.0, round(lot_size, 2)))
