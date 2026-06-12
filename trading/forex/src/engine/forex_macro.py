"""
Forex Macro Signal — Economic calendar rules and session-based biases.
Robust to DST changes for US High-Impact news releases.
"""
import time
from datetime import datetime, timezone, timedelta
from typing import Tuple, Dict, Optional

# High-impact events
HIGH_IMPACT_USD_EVENTS = [
    "Non-Farm Payrolls", "NFP",
    "CPI", "Core CPI",
    "Federal Funds Rate", "FOMC",
    "GDP", "Unemployment",
    "Retail Sales",
]

def get_us_eastern_time(utc_dt: datetime) -> datetime:
    """Converts a UTC datetime to US Eastern Time (EST/EDT) manually to avoid DST issues."""
    year = utc_dt.year
    
    # 2nd Sunday in March (DST starts)
    march_sun = 8
    for day in range(8, 15):
        if datetime(year, 3, day).weekday() == 6:
            march_sun = day
            break
            
    # 1st Sunday in November (DST ends)
    nov_sun = 1
    for day in range(1, 8):
        if datetime(year, 11, day).weekday() == 6:
            nov_sun = day
            break
            
    # DST starts at 07:00 UTC (02:00 EST) and ends at 06:00 UTC (02:00 EDT)
    dst_start = datetime(year, 3, march_sun, 7, 0, tzinfo=timezone.utc)
    dst_end = datetime(year, 11, nov_sun, 6, 0, tzinfo=timezone.utc)
    
    if dst_start <= utc_dt < dst_end:
        return utc_dt - timedelta(hours=4)  # EDT
    else:
        return utc_dt - timedelta(hours=5)  # EST

class ForexMacroSignal:
    def __init__(self):
        self._cache = {}
        self._cache_time = 0
        self._cache_ttl = 300

    def get_bias(self, symbol: str) -> dict:
        """Returns macro bias for a symbol."""
        now = datetime.now(timezone.utc)
        hour = now.hour
        weekday = now.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun

        # Weekend — no trading
        if weekday >= 5:
            return {"bias": "NEUTRAL", "strength": 0, "reason": "Weekend — market closed"}

        # Friday after 20:00 UTC — reduce activity
        if weekday == 4 and hour >= 20:
            return {"bias": "NEUTRAL", "strength": 20, "reason": "Friday close — reduce exposure"}

        # Monday open gap risk
        if weekday == 0 and hour < 2:
            return {"bias": "NEUTRAL", "strength": 30, "reason": "Monday open — watch for gaps"}

        # Session-based bias per symbol
        if symbol in ("EURUSDm", "GBPUSDm"):
            if 7 <= hour < 16:  # London session
                return {"bias": "BULLISH" if hour < 12 else "NEUTRAL",
                        "strength": 55, "reason": f"London session open (H={hour})"}
        elif symbol == "USDJPYm":
            if 0 <= hour < 8:  # Asia session
                return {"bias": "NEUTRAL", "strength": 50, "reason": "Asia session — JPY active"}
        elif symbol == "XAUUSDm":
            if 13 <= hour < 16:  # London+NY overlap
                return {"bias": "BULLISH", "strength": 60, "reason": "Gold: London+NY overlap — highest volume"}

        return {"bias": "NEUTRAL", "strength": 40, "reason": f"Normal session (H={hour})"}

    def should_avoid_trading(self, symbol: str, now_utc: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Determines whether to pause trading due to high-impact events like NFP.
        DST-aware: NFP is always at 8:30 AM Eastern Time on first Friday.
        """
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        now_est = get_us_eastern_time(now_utc)
        
        # Check for first Friday of the month (NFP day)
        # NFP is typically at 8:30 AM ET. Avoid trading between 8:25 AM and 8:45 AM ET.
        if now_est.weekday() == 4 and now_est.day <= 7:
            if now_est.hour == 8 and 25 <= now_est.minute < 45:
                return True, f"NFP release active (ET time {now_est.strftime('%H:%M')}) — avoid USD pairs"
                
        return False, ""
