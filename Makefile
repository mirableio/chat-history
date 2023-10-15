all:
	@echo "Nothing to do by default"
	@echo "Try 'make run'"

run:
	uvicorn app:app --reload --port 8080

install:
	pip install poetry
	poetry install
