all:
	@echo "Nothing to do by default"
	@echo "Try 'make run'"

run:
	uv run chat-history serve --port 8080

dev:
	uv run uvicorn chat_history.app:app --reload --port 8080

install:
	uv sync

test:
	uv run python -m unittest discover -s tests -v

tool-install:
	uv tool install -e .

tool-uninstall:
	uv tool uninstall chat-history
