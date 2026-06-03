.PHONY: immigration lite dev dev-lite test benchmark clean build-assets

# Docker Compose targets
immigration:
	docker compose -f docker-compose.yml -f docker-compose.immigration.yml up --build

lite:
	docker compose -f docker-compose.yml -f docker-compose.lite.yml up --build

# Local development targets
dev:
	CASEHUB_PRODUCT=immigration uvicorn app:app --host 0.0.0.0 --port 8001 --reload

dev-lite:
	CASEHUB_PRODUCT=lite DEFAULT_LOCALE=pt-BR uvicorn app:app --host 0.0.0.0 --port 8001 --reload

# Asset pipeline — minify CSS/JS and update static/assets/dashboard-manifest.json
build-assets:
	node scripts/build-dashboard-assets.mjs

# Testing
test:
	pytest

benchmark:
	pytest tests/benchmarks/ -v --benchmark-only 2>/dev/null || pytest tests/ -k benchmark -v

# Cleanup
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; \
	find . -type f -name '*.pyc' -delete 2>/dev/null; \
	find . -type f -name '*.pyo' -delete 2>/dev/null; \
	echo "Cleaned."
