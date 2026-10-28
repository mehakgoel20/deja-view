import json
import os
from urllib import response
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.vectorstores import FAISS


load_dotenv()

# Load dataset
with open("dataset/production_issues_75.json") as f:
    data = json.load(f)

# Convert dataset to documents
documents = []
metadata = []

for item in data:
    text = f"""
    Issue: {item['issue']}
    Causes: {', '.join(item['root_causes'])}
    Solutions: {', '.join(item['solutions'])}
    """
    documents.append(text)
    metadata.append(item)

# Create embeddings
embeddings = OpenAIEmbeddings()

# Create vector DB
vector_db = FAISS.from_texts(documents, embeddings)

# LLM
llm = ChatOpenAI(temperature=0.3)

# RCA function
# def analyze_issue(query):
#     docs = vector_db.similarity_search_with_score(query, k=3)

#     context = ""
#     similar_issues = []

#     for doc, score in docs:
#         context += doc.page_content + "\n"
#         similarity = 1 / (1 + score)
#         similar_issues.append({
#             "content": doc.page_content,
#             "similarity_score": float(similarity)
#         })

#     prompt = f"""
#     You are an expert Site Reliability Engineer.

#     Analyze the issue:
#     "{query}"

#     Using the context below:
#     {context}

#     Return strictly in JSON format:
#     {{
#         "root_causes": ["..."],
#         "solutions": ["..."],
#         "confidence": 0-1,
#         "explanation": "why these causes"
#     }}
#     """

#     response = llm.predict(prompt)
#     try:
#         parsed = json.loads(response)
#     except:
#         parsed = {
#             "error": "Invalid JSON from LLM",
#             "raw_output": response
#         }
#     return {
#         "analysis": parsed,
#         "similar_issues": similar_issues
#     }
def analyze_issue(query):
    docs = vector_db.similarity_search_with_score(query, k=3)

    # ✅ Convert distance → similarity (and FIX numpy issue)
    processed_docs = []
    for doc, score in docs:
        similarity = float(1 / (1 + score))  # 🔥 FIX HERE
        processed_docs.append((doc, similarity))

    top_similarity = float(processed_docs[0][1])

    # 🔥 THRESHOLD CHECK
    if top_similarity < 0.75:
        prompt = f"""
        You are an expert SRE engineer.

        Analyze this issue:
        "{query}"

        Return strictly in JSON:
{{
    "root_causes": ["cause1", "cause2", "cause3"],
    "solutions": ["solution1", "solution2", "solution3"],
    "confidence": 0.7,
    "explanation": "Explain why these causes are likely"
}}
        """

        response = llm.invoke(prompt).content  # ✅ FIXED

        try:
            parsed = json.loads(response)
        except:
            parsed = {
                "error": "Invalid JSON from LLM",
                "raw_output": response
            }

        return {
            "mode": "LLM_ONLY",
            "analysis": parsed,
            "similar_issues": []
        }

    # ✅ RAG FLOW
    context = "\n".join([doc.page_content for doc, _ in processed_docs])

    prompt = f"""
    You are an expert SRE engineer.

    Issue: {query}

    Context:
    {context}

    Return strictly in JSON:
    {{
        "root_causes": [],
        "solutions": [],
        "confidence": 0-1,
        "explanation": ""
    }}
    """

    response = llm.invoke(prompt).content  # ✅ FIXED

    try:
        parsed = json.loads(response)
    except:
        parsed = {
            "error": "Invalid JSON from LLM",
            "raw_output": response
        }

    return {
        "mode": "RAG",
        "analysis": parsed,
        "similar_issues": [
            {
                "content": doc.page_content,
                "similarity_score": float(sim)  # 🔥 FIX HERE
            }
            for doc, sim in processed_docs
        ]
    }