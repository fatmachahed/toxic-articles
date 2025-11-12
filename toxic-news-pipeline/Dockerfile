# Base image Python
FROM python:3.11-slim

# Définir le répertoire de travail
WORKDIR /app

# Installer les dépendances système nécessaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    zlib1g-dev \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copier les fichiers de requirements séparément
COPY requirements.txt requirements-torch.txt ./

# Installer d'abord les packages standards
RUN pip install --upgrade pip wheel setuptools
RUN pip install --default-timeout=300 --no-cache-dir -r requirements.txt

# Installer PyTorch (avec l'index officiel)
RUN pip install --default-timeout=300 --no-cache-dir -r requirements-torch.txt
RUN pip install --no-cache-dir papermill ipykernel jupyter sentencepiece protobuf


# Installer git et wget si nécessaire
RUN apt-get update && apt-get install -y git wget

# Précharger le modèle Hugging Face dans l'image
RUN python -c "from transformers import AutoTokenizer, AutoModelForSequenceClassification; \
               AutoTokenizer.from_pretrained('unitary/multilingual-toxic-xlm-roberta'); \
               AutoModelForSequenceClassification.from_pretrained('unitary/multilingual-toxic-xlm-roberta')"



# Copier tout le code source
COPY . .

# Définir le PYTHONPATH
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Télécharger les corpus NLTK nécessaires
RUN python -m nltk.downloader punkt stopwords

# Exposer le port de l'API
EXPOSE 8000

# Lancer FastAPI avec uvicorn
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
