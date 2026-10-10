import ollama
import json
import os
import pdfplumber

pdf_path=os.path.join(os.path.dirname(__file__),"...") #gotta add here later
output=os.path.join(os.path.dirname(__file__),"/data/json") 


#this should take each page with its chuk then through the use of llm there should output of the json
def extract_from_each_page(chunk):
    ...