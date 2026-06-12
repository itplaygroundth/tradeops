# tradeops — unified launcher
# Usage: make forex | crypto | control | all | stop | stop-orphans | test

include config/services.env
export

FOREX_PY := /home/alfred/tradeops/trading/forex/.venv/bin/python
FOREX_MODE ?= live
CRYPTO_MODE ?= live
CRYPTO_EXCHANGE ?= binance

.PHONY: help forex crypto control all stop stop-orphans test install

help:
	@echo "tradeops commands:"
	@echo "  make forex    - forex bot, $(FOREX_MODE)/demo mode (port $(FOREX_PORT))"
	@echo "  make crypto   - crypto bot, $(CRYPTO_MODE)/demo mode (port $(CRYPTO_PORT))"
	@echo "  make control  - control plane server (port $(CONTROL_PORT))"
	@echo "  make all      - everything in tmux session 'tradeops'"
	@echo "  make stop     - kill tmux session 'tradeops'"
	@echo "  make stop-orphans - kill old duplicate tradeops/legacy bot processes"
	@echo "  make test     - run python test suites"
	@echo "  make install  - npm install for control server/client"

forex:
	cd trading/forex/src && RECENT_SYMBOL_GUARD_ENABLED=false $(FOREX_PY) run.py --mode $(FOREX_MODE) --dashboard-port $(FOREX_PORT)

crypto:
	cd trading/crypto/src && DASHBOARD_PORT=$(CRYPTO_PORT) python3 run.py --mode $(CRYPTO_MODE) --exchange $(CRYPTO_EXCHANGE)

control:
	cd control/server && node server.js

all:
	tmux kill-session -t tradeops 2>/dev/null || true
	$(MAKE) stop-orphans
	tmux new-session -d -s tradeops -n forex 'make forex'
	tmux new-window -t tradeops -n crypto 'make crypto'
	tmux new-window -t tradeops -n control 'make control'
	@echo "started: tmux attach -t tradeops"

stop:
	tmux kill-session -t tradeops 2>/dev/null || true
	$(MAKE) stop-orphans
	@echo "stopped"

stop-orphans:
	@python3 scripts/stop_orphans.py

test:
	cd trading/forex && $(FOREX_PY) -m pytest tests/ -q
	cd trading/crypto && python3 -m pytest -q

install:
	cd control/server && npm install
	cd control/client && npm install
