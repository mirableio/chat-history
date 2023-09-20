import openai
import faiss
import numpy as np
import json
import sqlite3
from tqdm import tqdm


TYPE_CONVERSATION = "conversation"
TYPE_MESSAGE = "message"


def get_embedding(text):
    return openai.Embedding.create(input=text, 
                                   model="text-embedding-ada-002"
                                   )["data"][0]["embedding"]


def load_create_embeddings(path: str, conversations):

    def connect_db(db_name):
        conn = sqlite3.connect(db_name)
        c = conn.cursor()
        c.execute('''
        CREATE TABLE IF NOT EXISTS embeddings (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            conv_id TEXT NOT NULL,
            embedding BLOB NOT NULL
        );
        ''')
        conn.commit()
        return conn

    def load_embeddings(conn):
        c = conn.cursor()
        embeddings = {}
        try:
            for row in c.execute('SELECT id, type, conv_id, embedding FROM embeddings'):
                _id, _type, conv_id, embedding_bytes = row
                # Deserialize bytes to NumPy array
                embedding_array = np.frombuffer(embedding_bytes)
                embeddings[_id] = {
                    "type": _type,
                    "conv_id": conv_id,
                    "embedding": embedding_array.tolist()
                }
        except sqlite3.Error as e:
            print(f"SQLite error: {e}")
        return embeddings

    def save_embeddings(conn, embeddings):
        c = conn.cursor()
        for _id, embedding_data in embeddings.items():
            # Serialize NumPy array to bytes
            embedding_bytes = np.array(embedding_data["embedding"]).tobytes()
            try:
                c.execute("REPLACE INTO embeddings (id, type, conv_id, embedding) VALUES (?, ?, ?, ?)",
                        (_id, embedding_data["type"], embedding_data["conv_id"], embedding_bytes))
            except sqlite3.InterfaceError as e:
                print(f"Error inserting data into database: {e}")
        conn.commit()

    def generate_missing_embeddings(db_conn, conversations, embeddings):
        new_embeddings = 0
        embeddings_save = {}
        for conv in tqdm(conversations):
            if conv.title and conv.id not in embeddings:
                record = {
                    "type": TYPE_CONVERSATION,
                    "conv_id": conv.id,
                    "embedding": get_embedding(conv.title)
                }
                embeddings[conv.id] = record
                embeddings_save[conv.id] = record
                new_embeddings += 1

            for msg in conv.messages:
                if msg and msg.text and msg.id not in embeddings:
                    
                    record = {
                        "type": TYPE_MESSAGE,
                        "conv_id": conv.id,
                        "embedding": get_embedding(msg.text)
                    }
                    embeddings[msg.id] = record
                    embeddings_save[msg.id] = record
                    new_embeddings += 1

            if embeddings_save:
                save_embeddings(db_conn, embeddings_save)
                embeddings_save = {}
        return new_embeddings

    def build_faiss_index(embeddings):
        embeddings_ids = list(embeddings.keys())
        embeddings_np = np.array([np.array(embeddings[_id]["embedding"]) for _id in embeddings_ids]).astype('float32')
        d = embeddings_np.shape[1]
        index = faiss.IndexFlatL2(d)
        index.add(embeddings_np)
        return index, embeddings_ids
    
    db_conn = connect_db(path)

    embeddings = load_embeddings(db_conn)
    print(f"-- Loaded {len(embeddings)} embeddings")

    new_embeddings = 0
    missing_count = sum(1 for conv in conversations if conv.title and conv.id not in embeddings)
    if missing_count > 0:
        print(f"-- {missing_count} conversations don't have embeddings. Generating new ones...")
        new_embeddings = generate_missing_embeddings(db_conn, conversations, embeddings)

    if new_embeddings > 0:
        print(f"-- Created {new_embeddings} new embeddings")
    embeddings_index, embeddings_ids = build_faiss_index(embeddings)
    print(f"-- Built FAISS index with {embeddings_index.ntotal} embeddings")

    return embeddings, embeddings_ids, embeddings_index


def search_similar(query, embeddings_ids, embeddings_index, top_n=10):
    query_embedding = get_embedding(query)
    query_vector = np.array(query_embedding).astype('float32').reshape(1, -1)
    _, indices = embeddings_index.search(query_vector, top_n)
    similar_ids = [embeddings_ids[i] for i in indices[0]]
    return similar_ids[:top_n]


def openai_api_cost(model, input=0, output=0):
    pricing = {
        "gpt-3.5-turbo-4k": {
            "prompt": 0.0015,
            "completion": 0.002,
        },
        "gpt-3.5-turbo-16k": {
            "prompt": 0.003,
            "completion": 0.004,
        },
        "gpt-4-8k": {
            "prompt": 0.03,
            "completion": 0.06,
        },
        "gpt-4-32k": {
            "prompt": 0.06,
            "completion": 0.12,
        },
        "text-embedding-ada-002-v2": {
            "prompt": 0.0001,
            "completion": 0.0001,
        }
    }

    try:
        model_pricing = pricing[model]
    except:
        if 'gpt-4' in model:
            if input + output > 8192:
                model_pricing = pricing["gpt-4-32k"]
            else:
                model_pricing = pricing["gpt-4-8k"]
        elif 'gpt-3.5' in model:
            if input + output > 4096:
                model_pricing = pricing["gpt-3.5-turbo-16k"]
            else:
                model_pricing = pricing["gpt-3.5-turbo-4k"]
        else:
            model_pricing = pricing["gpt-3.5-turbo-4k"]
        
    if input > 0:
        return model_pricing["prompt"] * input / 10 # in cents
    elif output > 0:
        return model_pricing["completion"] * output / 10 # in cents
    else:
        raise ValueError("No token count specified")
