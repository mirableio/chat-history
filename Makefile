all:
	@echo "Nothing to do by default"
	@echo "Try 'make run'"

run:
	uv run uvicorn app:app --reload --port 8080

install:
	uv sync
