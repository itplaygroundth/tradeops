# tradeops — unified launcher
# Usage: make forex | crypto | control | all | dashboards-build | stop | stop-orphans | test

include config/services.env
-include .env
-include trading/crypto/.env
export

# Legacy root env keys are treated as Testnet credentials in demo mode only.
BINANCE_TESTNET_API_KEY ?= $(BINANCE_API_KEY)
BINANCE_TESTNET_API_SECRET ?= $(BINANCE_API_SECRET)

FOREX_PY := /home/alfred/tradeops/trading/forex/.venv/bin/python
FOREX_MODE ?= demo
CRYPTO_MODE ?= demo
CRYPTO_EXCHANGE ?= binance
FOREX_START_PAUSED ?= true
FOREX_DISABLE_ORDERS ?= true
FOREX_RECENT_SYMBOL_GUARD_ENABLED ?= true
CRYPTO_START_PAUSED ?= true
CRYPTO_FORCE_SIGNAL_ONLY ?= true

.PHONY: help forex crypto control all dashboards-build forex-dashboard-build crypto-dashboard-build stop stop-orphans test install

help:
	@echo "tradeops commands:"
	@echo "  make forex    - forex bot, $(FOREX_MODE)/demo mode (port $(FOREX_PORT))"
	@echo "  make crypto   - crypto bot, $(CRYPTO_MODE)/demo mode (port $(CRYPTO_PORT))"
	@echo "  make control  - control plane server (port $(CONTROL_PORT))"
	@echo "  make all      - everything in tmux session 'tradeops'"
	@echo "  make dashboards-build - build static mtai/crypto dashboards"
	@echo "  make stop     - kill tmux session 'tradeops'"
	@echo "  make stop-orphans - kill old duplicate tradeops/legacy bot processes"
	@echo "  make test     - run python test suites"
	@echo "  make install  - npm install for control server/client"

forex:
	cd trading/forex/src && START_PAUSED=$(FOREX_START_PAUSED) DISABLE_ORDERS=$(FOREX_DISABLE_ORDERS) RECENT_SYMBOL_GUARD_ENABLED=$(FOREX_RECENT_SYMBOL_GUARD_ENABLED) $(FOREX_PY) run.py --mode $(FOREX_MODE) --dashboard-port $(FOREX_PORT)

crypto:
	cd trading/crypto/src && START_PAUSED=$(CRYPTO_START_PAUSED) CRYPTO_FORCE_SIGNAL_ONLY=$(CRYPTO_FORCE_SIGNAL_ONLY) DASHBOARD_PORT=$(CRYPTO_PORT) python3 run.py --mode $(CRYPTO_MODE) --exchange $(CRYPTO_EXCHANGE)

control:
	cd control/server && node server.js

dashboards-build: forex-dashboard-build crypto-dashboard-build

forex-dashboard-build:
	cd trading/forex/dashboard-ui && npm run build

crypto-dashboard-build:
	cd trading/crypto/dashboard-ui && npm run build

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
	cd trading/forex/dashboard-ui && npm install
	cd trading/crypto/dashboard-ui && npm install
