import json
import os
import zipfile
import chromadb
import ollama

# Base path configurations
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
JSON_PATH = os.path.join(DATA_DIR, "json", "curriculum_data.json")  # Adjust to your exact file name
CHROMA_PATH = os.path.join(DATA_DIR, "chromadb")
ZIP_PATH = os.path.join(DATA_DIR, "chromadb.zip")


def ensure_chroma_unzipped():
    """Checks if chromadb folder exists; if not, extracts chromadb.zip automatically."""
    if not os.path.exists(CHROMA_PATH):
        if os.path.exists(ZIP_PATH):
            print(f"[RAG Setup] 'chromadb' directory not found. Extracting {ZIP_PATH}...")
            os.makedirs(DATA_DIR, exist_ok=True)
            with zipfile.ZipFile(ZIP_PATH, 'r') as zip_ref:
                zip_ref.extractall(DATA_DIR)
            print("[RAG Setup] ChromaDB extracted successfully!")
        else:
            print(f"[RAG Setup] Warning: Neither {CHROMA_PATH} nor {ZIP_PATH} was found.")


# Ensure database is unzipped prior to initializing persistent client
ensure_chroma_unzipped()

# Initializing ChromaDB
chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = chroma_client.get_or_create_collection(name="cdc_curriculumn_standards")


def initialize_vector_database():
    """Syncs JSON records into ChromaDB if the collection is not yet populated."""
    if not os.path.exists(JSON_PATH):
        print(f"[RAG] JSON source path '{JSON_PATH}' does not exist! Skipping JSON sync.")
        return

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    existing_count = collection.count()

    if existing_count >= len(data):
        print(f"[RAG] Vector store fully synced ({existing_count} records).")
        return

    print(f"[RAG] Syncing {len(data)} items into ChromaDB...")
    documents = []
    metadatas = []
    ids = []

    for item in data:
        doc_text = (
            f"Subject: {item['subject']} | Grade: {item['grade']} | "
            f"Topic: {item['topic']} | Competency: {item['competency']} | "
            f"Teaching Strategy: {item['teaching_strategy']}"
        )
        documents.append(doc_text)
        metadatas.append({
            "grade": int(item["grade"]),
            "subject": str(item["subject"]),
            "topic": str(item["topic"]),
            "source_file": str(item["source_file"])
        })
        ids.append(str(item["id"]))

    batch_size = 100
    total_batches = (len(documents) + batch_size - 1) // batch_size

    for i in range(0, len(documents), batch_size):
        batch_documents = documents[i:i + batch_size]
        batch_metadata = metadatas[i:i + batch_size]
        batch_ids = ids[i:i + batch_size]

        response = ollama.embed(model="nomic-embed-text", input=batch_documents)
        embeddings = response["embeddings"]

        collection.upsert(
            documents=batch_documents,
            embeddings=embeddings,
            metadatas=batch_metadata,
            ids=batch_ids
        )
        print(f"Processed batch {i // batch_size + 1} / {total_batches}...")

    print("[RAG] Vector database initialization complete!")


def query_curriculum_rag(user_query: str, grade_filter: int = None, subject_filter: str = None, top_k: int = 3):
    """Embeds user query, applies metadata filters, and retrieves context text."""
    try:
        response = ollama.embed(model="nomic-embed-text", input=user_query)
        query_embedding = response["embeddings"][0]
    except Exception as e:
        print(f"[RAG Warning] Ollama embedding call failed: {e}")
        return "CDC Curriculum Standards unavailable.", []

    where_conditions = []
    if grade_filter is not None:
        where_conditions.append({"grade": int(grade_filter)})
    if subject_filter is not None:
        where_conditions.append({"subject": str(subject_filter)})

    if len(where_conditions) == 1:
        where_filter = where_conditions[0]
    elif len(where_conditions) > 1:
        where_filter = {"$and": where_conditions}
    else:
        where_filter = None

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where_filter
    )

    if not results.get('documents') or not results['documents'][0]:
        return "No matching CDC curriculum standards found.", []

    retrieved_docs = results['documents'][0]
    retrieved_meta = results['metadatas'][0] if 'metadatas' in results and results['metadatas'] else [{}] * len(retrieved_docs)

    context_builder = []
    for idx, (doc, meta) in enumerate(zip(retrieved_docs, retrieved_meta), 1):
        subj = meta.get('subject', 'General')
        grd = meta.get('grade', 'N/A')
        context_builder.append(f"Standard {idx} [{subj} Grade {grd}]:\n{doc}")

    return "\n\n".join(context_builder), retrieved_meta


if __name__ == "__main__":
    initialize_vector_database()