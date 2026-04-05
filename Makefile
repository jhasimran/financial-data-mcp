run:
	python -m app.main

dev:
	uvicorn app.main:app --reload

mcp:
	python -m app.main

orchestrator:
	uvicorn app.main:app --host 0.0.0.0 --port 8000

orchestrator-env:
	uvicorn app.main:app --env-file .env --host 0.0.0.0 --port 8000

ui:
	cd ui && npm run dev

test:
	pytest
