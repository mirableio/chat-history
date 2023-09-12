# ChatGPT history

UI for browsing and searching OpenAI's ChatGPT conversations.

**Important**: This project is 100% unaffiliated with OpenAI.

Requires Python 3.10+

## Usage

1. [Export ChatGPT history](https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data)
2. Unzip the download, place `conversations.json` in the `data` folder
3. `make install`
4. `make run`
5. Open http://127.0.0.1:8000 in your browser
6. *Optional* - copy `secrets.template.toml` to `data/secrets.toml` and update OpenAI API key, then restart server. First run will take a while to create embeddings, ~30 min for 10MB JSON
