# AI Hedgefund Project - Command Center Makefile
# Operating System: Linux/macOS

.PHONY: help install run start-backend start-frontend clean

help:
	@echo "=========================================================================="
	@echo "                   ⚡ AI HEDGEFUND COMMAND TERMINAL ⚡"
	@echo "=========================================================================="
	@echo " Available commands:"
	@echo "  make install         - Install node modules for both client and server"
	@echo "  make run             - Run both backend (SQLite) & frontend (Vite) concurrently"
	@echo "  make start-backend   - Launch backend API server only (port 5001)"
	@echo "  make start-frontend  - Launch frontend developer server only (port 5173)"
	@echo "  make clean           - Wipe out node_modules, database files, and WAL logs"
	@echo "=========================================================================="

install:
	@echo "📦 Installing Backend Server dependencies..."
	@cd server && npm install
	@echo "📦 Installing Frontend Client dependencies..."
	@cd client && npm install
	@echo "✅ All dependencies installed successfully!"

run:
	@echo "🚀 Launching AI Hedgefund API Server and Vite Frontend concurrently..."
	@echo "   👉 Backend (API)  : http://localhost:5001"
	@echo "   👉 Frontend (UI)  : http://localhost:5173"
	@echo "   (Press Ctrl+C to terminate both servers)"
	@trap 'kill 0' INT; \
	(cd server && npm run start) & \
	(cd client && npm run dev) & \
	wait

start-backend:
	@echo "🚀 Launching Backend API Server only..."
	@cd server && npm run start

start-frontend:
	@echo "🚀 Launching Frontend Vite developer server only..."
	@cd client && npm run dev

clean:
	@echo "🧹 Cleaning temporary assets, database logs, and dependencies..."
	@rm -rf server/node_modules client/node_modules
	@rm -f server/hedgefund.db server/hedgefund.db-wal server/hedgefund.db-shm
	@echo "✨ Clean up completed successfully!"
