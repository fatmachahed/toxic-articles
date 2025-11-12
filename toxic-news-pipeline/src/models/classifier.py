import os
import torch
import numpy as np
from transformers import AutoTokenizer, AutoModelForSequenceClassification

# ========================================
# Configuration
# ========================================
MODEL_NAME = "unitary/multilingual-toxic-xlm-roberta"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

THRESHOLD_SLIGHTLY_TOXIC = float(os.getenv("TOXIC_SLIGHTLY_THRESHOLD", "0.3"))
THRESHOLD_VERY_TOXIC = float(os.getenv("TOXIC_VERY_THRESHOLD", "0.65"))
ARTICLE_THRESHOLD = float(os.getenv("TOXIC_ARTICLE_THRESHOLD", "0.5"))
MAX_TOKENS = 256  # Max tokens par segment

# ========================================
# Classifieur
# ========================================
class ToxicityClassifier:
    def __init__(self):
        print("Chargement du modèle...")
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
        self.model.to(DEVICE)
        self.model.eval()

        # Liste des labels liés à la toxicité
        self.id2label = self.model.config.id2label
        self.toxic_labels = [
            i for i, name in self.id2label.items()
            if "toxic" in name.lower() or
               "insult" in name.lower() or
               "obscene" in name.lower() or
               "threat" in name.lower() or
               "hate" in name.lower()
        ]

    def _predict_raw(self, texts):
        enc = self.tokenizer(
            texts,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=MAX_TOKENS
        ).to(DEVICE)

        with torch.no_grad():
            outputs = self.model(**enc)
            logits = outputs.logits
            probs = torch.sigmoid(logits)  # multi-label

        return probs.cpu().numpy()

    def _split_text(self, text, max_words=100):
        """Découpe le texte en segments pour éviter la dilution."""
        words = text.split()
        chunks = []
        for i in range(0, len(words), max_words):
            chunks.append(" ".join(words[i:i + max_words]))
        return chunks

    def predict(self, text: str):
        segments = self._split_text(text)
        segment_probs = [self._predict_raw([seg])[0] for seg in segments]

        # Score toxique = max des scores sur tous les segments
        toxic_score = max([float(np.mean([seg[i] for i in self.toxic_labels])) for seg in segment_probs])

        # Niveau de toxicité
        if toxic_score >= THRESHOLD_VERY_TOXIC:
            level = "very_toxic"
        elif toxic_score >= THRESHOLD_SLIGHTLY_TOXIC:
            level = "slightly_toxic"
        else:
            level = "non_toxic"

        prediction = "toxic" if toxic_score >= ARTICLE_THRESHOLD else "non_toxic"

        # Pour info par segment, on peut aussi stocker segment_probs si besoin
        per_label = {self.id2label[i]: round(float(np.mean([seg[i] for seg in segment_probs])), 3)
                     for i in range(len(self.id2label))}

        return {
            "prediction": prediction,
            "confidence": round(toxic_score, 3),
            "toxicity_level": level,
            "per_label": per_label
        }

# ========================================
# Tests
# ========================================
if __name__ == "__main__":
    clf = ToxicityClassifier()

    samples = [
        "Bonjour, j'espère que vous allez bien.",
        "Tu es un idiot et un menteur.",
        "On devrait te faire du mal, sale rat.",
        "Article neutre et informatif sans agressivité.",
        "Je déteste cette personne, c’est un imbécile fini.",
        "Très bon article, bien structuré et objectif."
    ]

    print("\n--- Résultats ---\n")
    for s in samples:
        out = clf.predict(s)
        print(f"{s[:60]:<60} => {out['prediction']:>10} ({out['toxicity_level']})  conf={out['confidence']:.3f}")
