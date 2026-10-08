#this file is only basically me testing out models seeingi time it takes for inference this can be ignored and has no use further
import ollama
import time

system_prompt="""You are an expert special education assistant in Nepal.
Your task is to convert teacher observations into structured Individualized Education Program (IEP) targets.

RULES:
1. Write ONLY in clear, natural Devanagari Nepali.
2. Do NOT use Hindi vocabulary or Bengali characters.
3. Include concrete local accommodations (e.g., Nepalese Rupees, local counting items).

EXAMPLE 1:
Observation: विद्यार्थीले १० सम्म मात्र गन्न सक्छ।
IEP Target:
- अल्पकालीन लक्ष्य: स्थानीय वस्तुहरू (नेपाली रुपैयाँका नोट वा काउन्टर) प्रयोग गरी २० सम्म गन्ती पहिचान गराउने।
- शिक्षण विधि: दैनिक ५ मिनेट पैसाको नक्कली कारोबार गराई गन्ती अभ्यास गराउने।

EXAMPLE 2:
Observation: अङ्क पहिचानमा समस्या छ।
IEP Target:
- अल्पकालीन लक्ष्य: थोप्ला जोडिएका रेखा (Dotted lines) प्रयोग गरी अङ्क ट्रेसिङ गराउने।
- शिक्षण विधि: स्पर्शजन्य कार्डहरू (Tactile cards) प्रयोग गर्ने।"""
teacher_notes="रामले कक्षा १ को गणितमा १० भन्दा ठूला संख्या गन्न सक्दैन। तर उसलाई पैसाको कारोबारमा रुचि छ।"

start_time=time.time()
response=ollama.chat(
    model="qwen2.5:7b-instruct",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"शिक्षकको टिप्पणी: {teacher_notes}"},
    ],
    options={
        "temperature": 0.1,       
        "top_p": 0.85,
        "repeat_penalty": 1.2,    
        "num_predict": 220,     
        "num_thread": 6,},
    stream=False,
)
elapsed=time.time()-start_time
print(f"Inference Time: {elapsed:.2f} seconds")
print("--- Generated Output ---")
print("SYSTEM PROMPT:")
print(system_prompt)

print("\nUSER PROMPT:")
print(f"शिक्षकको टिप्पणी: {teacher_notes}")
print(f"\nResponse:\n")
print(response["message"]["content"])