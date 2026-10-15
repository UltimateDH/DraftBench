import ollama
import json
import re
import os



def classifiy_intent_and_extract_params(user_prompt:str):
    system_prompt="""You are the Master Intent Classifier for DraftBench.
    Analyze the user prompt and return a strict JSON object with:
    {
    "intent": "chat" | "presentation" | "document" | "quiz",
    "grade": integer (1 to 12, default 7 if unspecified),
    "subject": string (e.g. "Mathematics", "Science", "English", "Nepali", "Social Studies"),
    "needs_autism_adaptations": boolean
    }
    CRITICAL: Output ONLY valid JSON."""

    response=ollama.chat(
        model="qwen2.5:7b-instruct",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        options={"temperature": 0.0}
    )

    try:
        raw = response["message"]["content"]
        clean_json = re.search(r'\{.*\}', raw, re.DOTALL).group(0)
        return json.loads(clean_json)
    except Exception: #for now i am just returning random class that i have more data of in RAG
        return {
            "intent": "document",
            "grade": 7,
            "subject": "Mathematics",
            "needs_autism_adaptations": True
        }



def run_unified_pipeline(user_prompt:str):
    print("Step[1]...Classifiying the intent of the user...")
    intent_data=classifiy_intent_and_extract_params(user_prompt=user_prompt)
    intent=intent_data.get("intent","document")
    grade=intent_data.get("grade","7")
    subject=intent_data.get("subject","Mathematics")
    need_asd=intent_data.get("needs_autism_adaptations",True)

    print("[Pipeline] Intent detected: {intent.upper()} | Grade: {grade} | Subject: {subject}")
    print("Step[2]...Using RAG...")
    