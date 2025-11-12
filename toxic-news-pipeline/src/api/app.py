import os
import io
from typing import Optional, Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, constr
from pymongo import MongoClient
import matplotlib.pyplot as plt

# ----------------------------------------
# Configuration du modèle
# ----------------------------------------
from src.models.classifier import ToxicityClassifier, MODEL_NAME, ARTICLE_THRESHOLD

# ---------- FastAPI ----------
app = FastAPI(
    title="Toxicity Prediction API",
    description="API de prédiction de toxicité de texte (multilingue XLM-R) et statistiques.",
    version="1.0.0"
)

# CORS (développement local)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000"
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Classifier ----------
_clf = ToxicityClassifier()

def predict_toxicity(text: str):
    return _clf.predict(text)

# ---------- MongoDB ----------
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "toxic_news")
STAT_COLLECTION = "statistics"

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
stat_collection = db[STAT_COLLECTION]

def get_latest_statistics():
    doc = stat_collection.find_one(sort=[("computed_at", -1)])
    if doc and "statistics" in doc:
        return doc["statistics"]
    return None

# ---------- Schemas ----------
class PredictRequest(BaseModel):
    text: constr(strip_whitespace=True, min_length=1) = Field(..., description="Texte à classifier")
    url: Optional[str] = Field(None, description="URL source, si disponible")
    title: Optional[str] = Field(None, description="Titre optionnel")

class PredictResponse(BaseModel):
    is_toxic: bool
    article_score: float
    per_label: Dict[str, float]
    model: str
    threshold: float
    stored: bool = False
    id: Optional[str] = None

# ---------- Endpoints ----------
@app.get("/health")
def health():
    return {"status": "ok", "app": "toxicity-api", "model": MODEL_NAME}

@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest):
    try:
        result = predict_toxicity(req.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model inference failed: {e}")

    return PredictResponse(
        is_toxic=result["prediction"] == "toxic",
        article_score=result["confidence"],
        per_label=result["per_label"],
        model=MODEL_NAME,
        threshold=ARTICLE_THRESHOLD,
        stored=False,
        id=None
    )

@app.get("/stats")
def stats_json():
    stats = get_latest_statistics()
    if not stats:
        return JSONResponse(content={"message": "Aucune statistique disponible."}, status_code=404)
    return stats

@app.get("/stats/plot")
def stats_plot():
    stats = get_latest_statistics()
    if not stats:
        return JSONResponse(content={"message": "Aucune statistique disponible."}, status_code=404)

    sites = list(stats.keys())
    slightly = [stats[s]["slightly_toxic_pct"] for s in sites]
    very = [stats[s]["very_toxic_pct"] for s in sites]

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(sites, slightly, label="Légèrement toxique", color="orange")
    ax.bar(sites, very, bottom=slightly, label="Très toxique", color="red")
    ax.set_ylabel("Pourcentage (%)")
    ax.set_title("Toxicité par site")
    ax.legend()
    plt.xticks(rotation=45)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)
    return StreamingResponse(buf, media_type="image/png")
