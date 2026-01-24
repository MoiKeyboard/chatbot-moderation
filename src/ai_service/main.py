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
            
        # 1. Embed
        embeddings = embedder.encode([text])
        
        # 2. Classify
        with torch.no_grad():
            inputs = torch.tensor(embeddings)
            outputs = classifier(inputs)
            
            # Extract Logits
            if hasattr(outputs, "logits"):
                logits = outputs.logits
            elif isinstance(outputs, (list, tuple)):
                logits = outputs[0]
            else:
                logits = outputs
                
            probs = torch.softmax(logits, dim=1).numpy()[0]
            
            # Map Labels (Assuming LionGuard Binary: 0=Safe, 1=Toxic)
            # Adjust if model config has specific id2label
            id2label = {0: "safe", 1: "toxic"}
            
            # Get highest probability label
            label_idx = probs.argmax()
            score = float(probs[label_idx])
            label = id2label.get(label_idx, "unknown")
            
            results.append({
                "label": label,
                "score": score,
                "all_scores": probs.tolist()
            })
            
    return {"predictions": results}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
