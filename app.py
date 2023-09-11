from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from markdown import markdown

from history import load_conversations


# Initialize FastAPI app
app = FastAPI()
api_app = FastAPI(title="API")

conversations = load_conversations('data/conversations.json')


# All conversation items
@api_app.get("/conversations")
def get_conversations():
    conversations_data = [{
        "id": conv.id, 
        "title": conv.title or "[Untitled]",
        "created": conv.created_str,
        } for conv in conversations]
    return JSONResponse(content=conversations_data)

# All messages from a specific conversation by its ID
@api_app.get("/conversations/{conv_id}/messages")
def get_messages(conv_id: str):
    conversation = next((conv for conv in conversations if conv.id == conv_id), None)
    if not conversation:
        return JSONResponse(content={"error": "Invalid conversation ID"}, status_code=404)

    #conversation = conversations[conv_id]
    messages = [{"text": markdown(msg.text),
                 "role": msg.role, 
                 "created": msg.created_str
                 } for msg in conversation.messages if msg]
    response = {
        "conversation_id": conversation.id,
        "messages": messages
    }
    return JSONResponse(content=response)

# Search conversations and messages
@api_app.get("/search")
def search_conversations(query: str = Query(..., min_length=3, description="Search query")):
    search_results = []

    for i, conv in enumerate(conversations):
        if query.lower() in (conv.title or "").lower():
            search_results.append({"type": "conversation", "id": i, "title": conv.title or "Untitled"})

        for msg in conv.messages:
            if msg and query.lower() in msg.text.lower():
                search_results.append({"type": "message", "conv_id": i, "text": markdown(msg.text), "role": msg.role, "created": msg.created_str})

        if len(search_results) >= 10:
            break

    return JSONResponse(content=search_results)


app.mount("/api", api_app)
app.mount("/", StaticFiles(directory="static", html=True), name="Static")
