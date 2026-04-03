run:
	python -m app.main

dev:
	uvicorn app.main:app --reload

test:
	pytest
