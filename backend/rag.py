import ollama
import json
import os
import chromadb

json_path=os.path.join(os.path.dirname(__file__),"data/json/") # reminder to myself: add full dir name here later
chroma_path=os.path.join(os.path.dirname(__file__),"data/chromadb")

#initialising the chroma db
chroma_client=chromadb.PersistentClient(path=chroma_path)
collection=chroma_client.get_or_create_collection(name="cdc_curriculumn_standards")


def initialize_vector_database():
    if not os.path.exists(json_path):
        print(f"{json_path} does not exist!")
        return
    with open(json_path,"r",encoding="utf-8") as f:
        data=json.load(f)

    existing_count=collection.count()

    if existing_count>=len(data):
        print("Everything in json has been synced to chromadb!")
        return

    print(f"Syncing {len(data)} into the chromadb!")
    documents=[]
    metadatas=[]
    ids=[]

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

    batch_size=100
    for i in range(0,len(documents),batch_size):
        batch_documents=documents[i:i+batch_size]
        batch_metadata=metadatas[i:i+batch_size]
        batch_ids=ids[i:i+batch_size]

        response=ollama.embed(model="nomic-embed-text",input=batch_documents)
        embeddings=response["embeddings"]

        collection.upsert(
            documents=batch_documents,
            embeddings=embeddings,
            metadatas=batch_metadata,
            ids=batch_ids
        )
        print(f"Processed batch {i // batch_size + 1} / {(len(documents) + batch_size - 1) // batch_size}...")
    print("Vector database initialization complete!")


#this function will help for query
import ollama

def query_curriculum_rag(user_query: str, grade_filter: int = None, subject_filter: str = None, top_k=3):
    """Embeds query, applies metadata filters, and returns raw context text."""
    query_embedding = ollama.embed(model="nomic-embed-text", input=user_query)["embeddings"][0]

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
    retrieved_meta = results['metadatas'][0] if 'metadatas' in results else [{}] * len(retrieved_docs)

    context_builder = []
    for idx, (doc, meta) in enumerate(zip(retrieved_docs, retrieved_meta), 1):
        subj = meta.get('subject', 'General')
        grd = meta.get('grade', 'N/A')
        context_builder.append(f"Standard {idx} [{subj} Grade {grd}]:\n{doc}")

    return "\n\n".join(context_builder), retrieved_meta


if __name__ == "__main__":
    # Ensure vector store is populated
    initialize_vector_database()

  
