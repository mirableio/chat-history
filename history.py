import json
import sys
from typing import List, Union, Optional
from collections import OrderedDict
from datetime import datetime
from pydantic.v1 import BaseModel # v2 throws warnings
import tiktoken


DEFAULT_MODEL_SLUG = "gpt-3.5-turbo"


class Author(BaseModel):
    role: str


class ContentPartMetadata(BaseModel):
    dalle: dict


class ContentPart(BaseModel):
    content_type: str
    asset_pointer: Optional[str]
    size_bytes: Optional[int]
    width: Optional[int]
    height: Optional[int]
    fovea: Optional[None]
    metadata: Optional[ContentPartMetadata]


class Content(BaseModel):
    content_type: str
    parts: Optional[List[Union[str, ContentPart]]]
    text: Optional[str]


class MessageMetadata(BaseModel):
    model_slug: Optional[str]
#     parent_id: Optional[str]


class Message(BaseModel):
    id: str
    author: Author
    create_time: Optional[float]
    update_time: Optional[float]
    content: Optional[Content]
    metadata: MessageMetadata

    @property
    def text(self) -> str:
        if self.content:
            if self.content.text:
                return self.content.text
            elif self.content.content_type == 'text' and self.content.parts: 
                return " ".join(str(part) for part in self.content.parts)
            elif self.content.content_type == 'multimodal_text':
                return "[TODO: process DALL-E and other multimodal]"
        return ""
    
    @property
    def role(self) -> str:
        return self.author.role

    @property
    def created(self) -> datetime:
        return datetime.fromtimestamp(self.create_time)

    @property
    def created_str(self) -> str:
        return self.created.strftime('%Y-%m-%d %H:%M:%S')
    
    @property
    def model_str(self) -> str:
        return self.metadata.model_slug or DEFAULT_MODEL_SLUG
    
    def count_tokens(self) -> int:
        try:
            encoding = tiktoken.encoding_for_model(self.model_str)
        except KeyError:
            encoding = tiktoken.encoding_for_model(DEFAULT_MODEL_SLUG)
        return len(encoding.encode(self.text, disallowed_special=()))


class MessageMapping(BaseModel):
    id: str
    message: Optional[Message]


class Conversation(BaseModel):
    id: str
    title: Optional[str]
    create_time: float
    update_time: float
    mapping: OrderedDict[str, MessageMapping]

    @property
    def messages(self) -> List:
        return [msg.message for k, msg in self.mapping.items() if msg.message and msg.message.text]

    @property
    def created(self) -> datetime:
        return datetime.fromtimestamp(self.create_time)#.strftime('%Y-%m-%d %H:%M:%S')

    @property
    def created_str(self) -> str:
        return self.created.strftime('%Y-%m-%d %H:%M:%S')

    @property
    def updated(self) -> datetime:
        return datetime.fromtimestamp(self.update_time)

    @property
    def updated_str(self) -> str:
        return self.updated.strftime('%Y-%m-%d %H:%M:%S')

    @property
    def title_str(self) -> str:
        return self.title or '[Untitled]'

    @property
    def total_length(self) -> int:
        start_time = self.created
        end_time = max(msg.created for msg in self.messages) if self.messages else start_time
        return (end_time - start_time).total_seconds()



def load_conversations(path: str) -> List[Conversation]:
    with open(path, 'r') as f:
        conversations_json = json.load(f)

    # Load the JSON data into these models
    try:
        conversations = [Conversation(**conv) for conv in conversations_json]
        success = True
    except Exception as e:
        print(str(e))
        sys.exit(1)

    print(f"-- Loaded {len(conversations)} conversations")
    return conversations
