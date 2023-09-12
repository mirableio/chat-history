import openai
import faiss
import numpy as np
import json
from tqdm import tqdm


TYPE_CONVERSATION = "conversation"
TYPE_MESSAGE = "message"


def get_embedding(text):
    return openai.Embedding.create(input=text, 
                                   model="text-embedding-ada-002"
                                   )["data"][0]["embedding"]

def load_create_embeddings(path: str, conversations):
    try:
        with open(path, "r") as f:
            embeddings = json.load(f)
        print(f"-- Loaded {len(embeddings)} embeddings")
    except:
        print("-- No embeddings found. Generating new ones...")
        for conv in tqdm(conversations):
            if conv.title:
                embedding = get_embedding(conv.title)
                embeddings[conv.id] = {
                    "type": TYPE_CONVERSATION,
                    "conv_id": conv.id,
                    "embedding": embedding
                }
            for msg in conv.messages:
                if msg and msg.text:
                    embedding = get_embedding(msg.text)
                    embeddings[msg.id] = {
                        "type": TYPE_MESSAGE,
                        "conv_id": conv.id,
                        "embedding": embedding
                    }

        with open("data/embeddings.json", "w") as f:
            json.dump(embeddings, f)
        print(f"-- Created {len(embeddings)} embeddings")

    embeddings_ids = list(embeddings.keys())
    embeddings_np = [np.array(embeddings[_id]["embedding"]) for _id in embeddings_ids]

    # FAISS works with float32 data type
    embeddings_np = np.array(embeddings_np).astype('float32')

    # Build the index
    d = embeddings_np.shape[1]  # dimension
    embeddings_index = faiss.IndexFlatL2(d)
    embeddings_index.add(embeddings_np)
    print(f"-- Built FAISS index with {embeddings_index.ntotal} embeddings")

    return embeddings, embeddings_ids, embeddings_index


def search_similar(query, embeddings_ids, embeddings_index, top_n=10):
    query_embedding = get_embedding(query)
    query_vector = np.array(query_embedding).astype('float32').reshape(1, -1)
    _, indices = embeddings_index.search(query_vector, top_n)
    similar_ids = [embeddings_ids[i] for i in indices[0]]
    return similar_ids[:top_n]
