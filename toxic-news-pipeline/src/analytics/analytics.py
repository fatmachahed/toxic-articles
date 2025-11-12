"""
Service de prédiction de toxicité avec stockage MongoDB.
Analyse tous les articles collectés et stocke les résultats de prédiction.
"""

import os
from datetime import datetime, timezone
from typing import Dict, Optional
from pymongo import MongoClient
from src.models.classifier import ToxicityClassifier  # Import direct du classifieur validé

# ============================================================================ 
# CONFIGURATION
# ============================================================================

class PredictorConfig:
    """Configuration du service de prédiction"""
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB = os.getenv("MONGO_DB", "toxic_news")
    
    # Collections
    ARTICLES_COLLECTION = "articles"
    PREDICTIONS_COLLECTION = "predictions"

# ============================================================================ 
# SERVICE DE PRÉDICTION
# ============================================================================

class ToxicityPredictor:
    """Service de prédiction de toxicité avec stockage des résultats."""

    def __init__(self):
        # Connexion MongoDB
        self.client = MongoClient(PredictorConfig.MONGO_URI)
        self.db = self.client[PredictorConfig.MONGO_DB]
        self.articles = self.db[PredictorConfig.ARTICLES_COLLECTION]
        self.predictions = self.db[PredictorConfig.PREDICTIONS_COLLECTION]

        # Crée les index
        self._create_indexes()

        # Initialise le classifieur
        print("Chargement du modèle de toxicité...")
        self.classifier = ToxicityClassifier()
        print("Modèle prêt\n")

    def _create_indexes(self):
        """Crée les index MongoDB pour optimiser les requêtes"""
        try:
            self.predictions.create_index("url", unique=True)
            self.predictions.create_index("predicted_at")
            self.predictions.create_index("site")
        except Exception as e:
            print(f"⚠ Warning index creation: {e}")

    def predict_text(self, text: str, url: Optional[str] = None) -> Dict:
        """Prédit la toxicité d'un texte et stocke le résultat."""
        if not text or not text.strip():
            return {"error": "Le texte ne peut pas être vide", "prediction": None}

        result = self.classifier.predict(text)
        prediction_doc = {
            "text": text[:1000],
            "url": url,
            "prediction": result["prediction"],
            "confidence": result["confidence"],
            "toxicity_level": result["toxicity_level"],
            "predicted_at": datetime.now(timezone.utc)
        }

        try:
            inserted = self.predictions.insert_one(prediction_doc)
            prediction_doc["_id"] = str(inserted.inserted_id)
            return {"success": True, "prediction": prediction_doc}
        except Exception as e:
            return {"success": False, "error": str(e), "prediction": prediction_doc}

    def predict_all_articles(self):
        """Analyse tous les articles et stocke les prédictions."""
        print("=== Analyse de toxicité de tous les articles ===\n")

        # Récupère tous les articles
        cursor = self.articles.find({})
        articles_list = list(cursor)
        total = len(articles_list)

        if total == 0:
            print("Aucun article dans la base.")
            return

        print(f"Total articles à analyser: {total}\n")

        # Statistiques
        stats = {
            "processed": 0,
            "success": 0,
            "errors": 0,
            "toxic": 0,
            "non_toxic": 0,
            "slightly_toxic": 0,
            "very_toxic": 0
        }

        for i, article in enumerate(articles_list, 1):
            url = article.get("url", "")
            title = article.get("title", "")
            content = article.get("content", "")
            site = article.get("site", "")

            if not content or not content.strip():
                print(f"[{i}/{total}] Skip (pas de contenu): {url}")
                stats["processed"] += 1
                continue

            print(f"[{i}/{total}] Analyse: {title[:50]}...")
            result = self.classifier.predict(content)

            prediction_doc = {
                "url": url,
                "site": site,
                "title": title,
                "text": content[:1000],
                "prediction": result["prediction"],
                "confidence": result["confidence"],
                "toxicity_level": result["toxicity_level"],
                "predicted_at": datetime.now(timezone.utc),
                "article_id": article.get("_id")
            }

            try:
                self.predictions.insert_one(prediction_doc)
                stats["success"] += 1
                stats[result["toxicity_level"]] += 1
                if result["prediction"] == "toxic":
                    stats["toxic"] += 1
                else:
                    stats["non_toxic"] += 1

                print(f"  → {result['prediction']} ({result['confidence']:.2%}) - {result['toxicity_level']}")
            except Exception as e:
                stats["errors"] += 1
                print(f"  → Erreur: {e}")

            stats["processed"] += 1

        self._print_analysis_summary(stats)

    def get_statistics_by_site(self) -> Dict:
        """Calcule les statistiques de toxicité par site."""
        pipeline = [
            {
                "$group": {
                    "_id": {"site": "$site", "toxicity_level": "$toxicity_level"},
                    "count": {"$sum": 1}
                }
            }
        ]

        results = list(self.predictions.aggregate(pipeline))
        site_stats = {}

        for res in results:
            site = res["_id"]["site"]
            level = res["_id"]["toxicity_level"]
            count = res["count"]
            if site not in site_stats:
                site_stats[site] = {"total": 0, "non_toxic": 0, "slightly_toxic": 0, "very_toxic": 0}
            site_stats[site][level] = count
            site_stats[site]["total"] += count

        stats_with_percentages = {}
        for site, counts in site_stats.items():
            total = counts["total"]
            if total > 0:
                stats_with_percentages[site] = {
                    "total_articles": total,
                    "non_toxic_count": counts["non_toxic"],
                    "slightly_toxic_count": counts["slightly_toxic"],
                    "very_toxic_count": counts["very_toxic"],
                    "non_toxic_pct": round(counts["non_toxic"] / total * 100, 2),
                    "slightly_toxic_pct": round(counts["slightly_toxic"] / total * 100, 2),
                    "very_toxic_pct": round(counts["very_toxic"] / total * 100, 2)
                }

        self._save_statistics(stats_with_percentages)
        return stats_with_percentages

    def _save_statistics(self, stats: Dict):
        """Sauvegarde les statistiques dans MongoDB"""
        stats_doc = {"computed_at": datetime.now(timezone.utc), "statistics": stats}
        try:
            self.db["statistics"].insert_one(stats_doc)
            print("✓ Statistiques sauvegardées")
        except Exception as e:
            print(f"Erreur sauvegarde statistiques: {e}")

    def _print_analysis_summary(self, stats: Dict):
        """Affiche le résumé de l'analyse"""
        print("\n" + "="*50)
        print("RÉSUMÉ DE L'ANALYSE")
        print("="*50)
        print(f"Articles traités: {stats['processed']}")
        print(f"Succès: {stats['success']}")
        print(f"Erreurs: {stats['errors']}")
        print(f"\nRépartition:")
        print(f"  - Non toxiques: {stats['non_toxic']}")
        print(f"  - Légèrement toxiques: {stats['slightly_toxic']}")
        print(f"  - Très toxiques: {stats['very_toxic']}")
        print("="*50 + "\n")

    def display_statistics(self):
        stats = self.get_statistics_by_site()
        if not stats:
            print("Aucune statistique disponible.")
            return

        print("\n" + "="*80)
        print("STATISTIQUES DE TOXICITÉ PAR SITE")
        print("="*80)
        print(f"{'Site':<30} {'Total':<8} {'Non tox. %':<12} {'Légèr. %':<12} {'Très %':<10}")
        print("-"*80)

        sorted_sites = sorted(
            stats.items(),
            key=lambda x: x[1]["slightly_toxic_pct"] + x[1]["very_toxic_pct"],
            reverse=True
        )

        for site, data in sorted_sites:
            print(f"{site:<30} {data['total_articles']:<8} {data['non_toxic_pct']:<11.2f}% "
                f"{data['slightly_toxic_pct']:<11.2f}% {data['very_toxic_pct']:<9.2f}%")

        print("="*80 + "\n")
        if sorted_sites:
            most_toxic = sorted_sites[0]
            print(f"🔴 Site le plus toxique: {most_toxic[0]}")
            total_toxic = most_toxic[1]["slightly_toxic_pct"] + most_toxic[1]["very_toxic_pct"]
            print(f"   Toxicité totale: {total_toxic:.2f}%")
            print(f"   Non toxique: {most_toxic[1]['non_toxic_pct']:.2f}%\n")



# ============================================================================ 
# FONCTION PRINCIPALE
# ============================================================================

def main():

    predictor = ToxicityPredictor()
    predictor.predict_all_articles()  # Analyse tous les articles
    predictor.display_statistics()


if __name__ == "__main__":
    main()
