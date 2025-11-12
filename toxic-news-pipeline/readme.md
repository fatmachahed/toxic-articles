# Toxic News Pipeline

## Description

**Toxic News Pipeline** est un projet automatisé de collecte et d’analyse de la toxicité dans les articles de presse en ligne.  
Il scrape les articles depuis plusieurs sites d’actualité, stocke les données dans **MongoDB** et fournit une **API REST** pour prédire la toxicité et visualiser des statistiques.

---

## Objectifs

- Détecter automatiquement le contenu toxique dans les articles de presse.
- Fournir une API REST pour la prédiction de toxicité.
- Visualiser les tendances de toxicité par site web.
- Offrir une solution conteneurisée simple à déployer.

---

## Fonctionnalités

### 1. Collecte de données

- Scraping automatique via les flux RSS de médias français.
- Extraction du texte complet et nettoyage des contenus.
- Stockage structuré dans MongoDB avec métadonnées détaillées (titre, URL, date, site source, longueur du texte…).

### 2. Analyse de toxicité

- Modèle **multilingue XLM-R** pour la classification multi-niveaux :
  - `non_toxic`
  - `slightly_toxic`
  - `very_toxic`
- Découpage en segments pour traiter les textes longs.
- Calcul d’un score global par article.

### 3. API REST

- Endpoint `/predict` : prédiction en temps réel d’un texte ou article.
- Endpoint `/stats` : statistiques agrégées par site ou période.
- Endpoint `/stats/plot` : graphiques de toxicité par site.
- Endpoint `/health` : vérification de l’état du service.

### 4. Visualisation

- Graphiques empilés représentant la proportion d’articles légèrement et très toxiques par site.
- Identification du site le plus toxique.
- Export possible pour analyses complémentaires.

### 5. Infrastructure

- Conteneurisation complète avec **Docker**.
- Orchestration via **Docker Compose**.
- Configuration via variables d’environnement pour adapter le comportement du scraper et de l’API.

---

## Installation rapide

### Prérequis

- Docker 20.10+
- Docker Compose 2.0+

### Lancer le projet

```bash
# 1. Cloner le repository
git clone <votre-repository>
cd toxic-news-pipeline

# 2. Construire et lancer les services en arrière-plan
docker compose up --build -d

# 3. Accéder aux services
# Documentation interactive de l’API : http://localhost:8000/docs
# MongoDB : localhost:27017
```
