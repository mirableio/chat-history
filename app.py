from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from markdown import markdown

from history import load_conversations


# Initialize FastAPI app
app = FastAPI()
api_app = FastAPI(title="API")

conversations = load_conversations('conversations.json')


# All conversation titles and their IDs
@api_app.get("/conversations")
def get_conversations():
    conversations_data = [{"id": i, "title": conv.title or "Untitled"} for i, conv in enumerate(conversations)]
    return JSONResponse(content=conversations_data)

# All messages from a specific conversation by its ID
@api_app.get("/conversations/{conv_id}/messages")
def get_messages(conv_id: int):
    if conv_id < 0 or conv_id >= len(conversations):
        return JSONResponse(content={"error": "Invalid conversation ID"}, status_code=404)

    conversation = conversations[conv_id]
    messages = [{"text": markdown(msg.text),
                 "role": msg.role, 
                 "created": msg.created_str
                 } for msg in conversation.messages if msg]
    response = {
        "conversation_id": conversation.id,
        "messages": messages
    }
    return JSONResponse(content=response)


app.mount("/api", api_app)
app.mount("/", StaticFiles(directory="static", html=True), name="Static")
