.PHONY: setup test lint run docker-build docker-run

setup:
	python3 -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip && pip install -e .[dev] && playwright install chromium

test:
	PYTHONPATH=src pytest

lint:
	ruff check .

run:
	PYTHONPATH=src python3 -m abs2sg.main

docker-build:
	docker compose build

docker-run:
	docker compose up --build
