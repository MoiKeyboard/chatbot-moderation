from fastapi import FastAPI, Request
from sentence_transformers import SentenceTransformer
from transformers import AutoModel, AutoConfig
import torch
import os
import uvicorn

app = FastAPI()

# Configuration
# Allow override for testing (e.g. "sentence-transformers/all-mpnet-base-v2")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "google/embeddinggemma-300m")
CLASSIFIER_MODEL = "govtech/lionguard-2-lite"
HF_TOKEN = os.getenv("HF_TOKEN")

print(f"Loading Models: {EMBEDDING_MODEL} + {CLASSIFIER_MODEL}...")

# Authenticate for Gated Models (Required for Gemma)
if HF_TOKEN:
    import huggingface_hub
    huggingface_hub.login(token=HF_TOKEN)
    print("Authenticated with Hugging Face.")

# Load Models (Global Scope for Warm Start)
# trust_remote_code=True is essential for LionGuard
embedder = SentenceTransformer(EMBEDDING_MODEL, device="cpu", trust_remote_code=True)
classifier = AutoModel.from_pretrained(CLASSIFIER_MODEL, trust_remote_code=True).to("cpu")
classifier.eval()

print("Models Loaded Successfully.")

@app.get("/health")
def health():
    """Vertex AI Health Check"""
    return {"status": "alive"}

@app.post("/predict")
async def predict(request: Request):
    """
    Vertex AI Prediction Endpoint.
    Expected Format: {"instances": [{"text": "message"}]}
    """
    data = await request.json()
    instances = data.get("instances", [])
    results = []

    for inst in instances:
        text = inst.get("text", "")
        if not text:
            continue
            
        # 1. Format (Crucial Step: Add Prompt)
        # Source: https://huggingface.co/govtech/lionguard-2-lite/blob/main/inference.py
        formatted_text = f"task: classification | query: {text}"
            
        # 2. Embed
        embeddings = embedder.encode([formatted_text])
        
        # 3. Classify (Use native predict method for LionGuard)
        if hasattr(classifier, "predict"):
             # Returns: {"binary": [0.1], "hateful_l1": [0.9]...}
             results_dict = classifier.predict(embeddings)
             
             inst_results = []
             for category, scores in results_dict.items():
                 # scores is a list/array, get first item
                 score = float(scores[0])
                 inst_results.append({"label": category, "score": score})
             
             results.append(inst_results)
             
        else:
            # Fallback (Should not happen for LionGuard)
            with torch.no_grad():
                inputs = torch.tensor(embeddings)
                outputs = classifier(inputs)
                # ... (basic fallback omitted for brevity, assuming trust_remote_code=True works)
                results.append([])

    # Flatten logic to match client expectation 
    # Client expects {"predictions": [[{"label":..., "score":...}]]}
    return {"predictions": results}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
