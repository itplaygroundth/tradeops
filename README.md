# tradeops — Unified Trading Operations Monorepo

รวม 3 ระบบ: forex bot (MT5/Exness), crypto bot (Binance/Bybit), control plane

```
tradeops/
├── trading/
│   ├── forex/    # MTAI — Python, port 3003 (เดิม ~/mtai)
│   └── crypto/   # Crypto AI — Python, port 3006 (เดิม ~/crypto-ai)
├── control/      # Hedgefund control plane — Node+React, port 5001
├── config/services.env   # service registry (ports/URLs)
└── Makefile      # make forex|crypto|control|all|stop|test
```

## Quick Start

```bash
make all      # ทุก service ใน tmux session 'tradeops'
make stop     # หยุดทั้งหมด
make test     # pytest ทั้ง 2 engine
```

## External

- MT5 bridge: `MT5_BRIDGE_URL` (Windows VM :8888)
- MADS agent OS: `MADS_API_URL` (:4311) — แยก repo, เชื่อมผ่าน HTTP
