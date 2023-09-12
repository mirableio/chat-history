import openai
import faiss
import numpy as np
import json
import os
from tqdm import tqdm


TYPE_CONVERSATION = "conversation"
TYPE_MESSAGE = "message"


def get_embedding(text):
    return openai.Embedding.create(input=text, 
                                   model="text-embedding-ada-002"
                                   )["data"][0]["embedding"]


def load_create_embeddings(path: str, conversations):

    def load_embeddings(path: str):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            print("Error decoding JSON from embeddings file.")
            return {}

    def save_embeddings(embeddings, path: str):
        with open(path, "w") as f:
            json.dump(embeddings, f)

    def generate_missing_embeddings(conversations, embeddings, path: str):
        count = 0
        batch_size = 10  # Save every 10 conversations
        for conv in tqdm(conversations):
            updated = False  # Flag to check if we updated the embeddings dict
            if conv.title and conv.id not in embeddings:
                embeddings[conv.id] = {
                    "type": TYPE_CONVERSATION,
                    "conv_id": conv.id,
                    "embedding": get_embedding(conv.title)
                }
                updated = True

            for msg in conv.messages:
                if msg and msg.text and msg.id not in embeddings:
                    embeddings[msg.id] = {
                        "type": TYPE_MESSAGE,
                        "conv_id": conv.id,
                        "embedding": get_embedding(msg.text)
                    }
                    updated = True

            if updated:
                count += 1

            if count > 0 and count % batch_size == 0:
                save_embeddings(embeddings, path)

    def build_faiss_index(embeddings):
        embeddings_ids = list(embeddings.keys())
        embeddings_np = np.array([np.array(embeddings[_id]["embedding"]) for _id in embeddings_ids]).astype('float32')
        d = embeddings_np.shape[1]
        index = faiss.IndexFlatL2(d)
        index.add(embeddings_np)
        return index, embeddings_ids

    embeddings = load_embeddings(path)
    print(f"-- Loaded {len(embeddings)} embeddings")

    missing_count = sum(1 for conv in conversations if conv.id not in embeddings)
    if missing_count > 0:
        print(f"-- {missing_count} conversations don't have embeddings. Generating new ones...")
        generate_missing_embeddings(conversations, embeddings, path)
        save_embeddings(embeddings, path)  # Final save

    print(f"-- Created {len(embeddings)} embeddings")
    embeddings_index, embeddings_ids = build_faiss_index(embeddings)
    print(f"-- Built FAISS index with {embeddings_index.ntotal} embeddings")

    return embeddings, embeddings_ids, embeddings_index


def search_similar(query, embeddings_ids, embeddings_index, top_n=10):
    query_embedding = get_embedding(query)
    query_vector = np.array(query_embedding).astype('float32').reshape(1, -1)
    _, indices = embeddings_index.search(query_vector, top_n)
    similar_ids = [embeddings_ids[i] for i in indices[0]]
    return similar_ids[:top_n]
