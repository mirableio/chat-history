from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from markdown import markdown
from collections import defaultdict

from history import load_conversations
from utils import time_group


# Initialize FastAPI app
app = FastAPI()
api_app = FastAPI(title="API")

conversations = load_conversations('data/conversations.json')


# All conversation items
@api_app.get("/conversations")
def get_conversations():
    conversations_data = [{
        "group": time_group(conv.created),
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

    messages = [{"text": markdown(msg.text),
                 "role": msg.role, 
                 "created": msg.created_str
                 } for msg in conversation.messages if msg]
    response = {
        "conversation_id": conversation.id,
        "messages": messages
    }
    return JSONResponse(content=response)


@api_app.get("/activity")
def get_activity():
    activity_by_day = defaultdict(int)

    for conversation in conversations:
        for message in conversation.messages:
            day = message.created.date()
            activity_by_day[day] += 1
    
    activity_by_day = {str(k): v for k, v in sorted(dict(activity_by_day).items())}

    return JSONResponse(content=activity_by_day)


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
