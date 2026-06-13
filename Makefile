# Stock Intelligence Platform — test runner
# Usage:
#   make test            run all tests (backend + frontend)
#   make test-backend    run Python/pytest tests only
#   make test-frontend   run Vitest (TypeScript) tests only
#
# Backend expects Python env with requirements.txt installed.
# Frontend expects pnpm installed (or npm: swap pnpm for npm in test-frontend).

.PHONY: test test-backend test-frontend test-playwright

test: test-backend test-frontend

test-backend:
	@echo "=== Backend (pytest) ==="
	python -m pytest tests/ -v --tb=short

test-frontend:
	@echo "=== Frontend (vitest) ==="
	cd frontend && pnpm exec vitest run --reporter verbose

# Playwright e2e tests require: Next.js dev server on :3001 (or will auto-start)
# First run: cd frontend && pnpm exec playwright install chromium
test-playwright:
	@echo "=== Playwright (mobile 380px) ==="
	cd frontend && pnpm exec playwright test --project=mobile-380
