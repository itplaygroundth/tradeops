# tradeops — unified launcher
# Usage: make forex | crypto | control | all | stop | test

include config/services.env
export

FOREX_PY := /home/alfred/mtai/.venv/bin/python

.PHONY: help forex crypto control all stop test install

help:
	@echo "tradeops commands:"
	@echo "  make forex    - forex bot, paper mode (port $(FOREX_PORT))"
	@echo "  make crypto   - crypto bot, paper mode (port $(CRYPTO_PORT))"
	@echo "  make control  - control plane server (port $(CONTROL_PORT))"
	@echo "  make all      - everything in tmux session 'tradeops'"
	@echo "  make stop     - kill tmux session 'tradeops'"
	@echo "  make test     - run python test suites"
	@echo "  make install  - npm install for control server/client"

forex:
	cd trading/forex/src && $(FOREX_PY) run.py --mode paper --dashboard-port $(FOREX_PORT)

crypto:
	cd trading/crypto/src && DASHBOARD_PORT=$(CRYPTO_PORT) python3 run.py --mode paper --exchange binance

control:
	cd control/server && node server.js

all:
	tmux new-session -d -s tradeops -n forex 'make forex'
	tmux new-window -t tradeops -n crypto 'make crypto'
	tmux new-window -t tradeops -n control 'make control'
	@echo "started: tmux attach -t tradeops"

stop:
	tmux kill-session -t tradeops 2>/dev/null || true
	@echo "stopped"

test:
	cd trading/forex && $(FOREX_PY) -m pytest tests/ -q
	cd trading/crypto && python3 -m pytest -q

install:
	cd control/server && npm install
	cd control/client && npm install
