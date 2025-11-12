"""
Module de scraping d'articles de presse avec stockage MongoDB.
Collecte des articles via RSS et extraction du contenu textuel.
"""
import os
import re
import time
import calendar
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import feedparser
import requests
import trafilatura
from pymongo import MongoClient, errors
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Configuration centralisée du scraper"""
    USER_AGENT = os.getenv(
        "SCRAPER_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    MIN_CHARS = int(os.getenv("MIN_ARTICLE_CHARS", "100"))
    TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", "50"))
    MAX_PER_FEED = int(os.getenv("SCRAPER_MAX_PER_FEED", "50"))
    SLEEP_TIME = float(os.getenv("SCRAPER_POLITE_SLEEP", "0.15"))
    MAX_AGE_DAYS = int(os.getenv("SCRAPER_MAX_AGE_DAYS", "30"))
    
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB = os.getenv("MONGO_DB", "toxic_news")


RSS_SOURCES = {
    "https://www.humanite.fr/": [
        "https://www.humanite.fr/rss.xml",
        "https://www.humanite.fr/rss/politique.xml",
        "https://www.humanite.fr/rss/economie.xml",
        "https://www.humanite.fr/rss/culture.xml",
    ],
    "https://www.gamespot.com/": [
        "https://www.gamespot.com/feeds/mashup/",
    ],
    "https://www.marianne.net/": [
        "https://www.marianne.net/rss.xml",
        "https://www.marianne.net/rss/politique.xml",
        "https://www.marianne.net/rss/economie.xml",
        "https://www.marianne.net/rss/international.xml",
    ],
    "https://www.lemonde.fr/": [
        "https://www.lemonde.fr/rss/une.xml",
        "https://www.lemonde.fr/international/rss_full.xml",
        "https://www.lemonde.fr/economie/rss_full.xml",
        "https://www.lemonde.fr/politique/rss_full.xml",
        "https://www.lemonde.fr/culture/rss_full.xml",
        "https://www.lemonde.fr/sciences/rss_full.xml",
        "https://www.lemonde.fr/societe/rss_full.xml",
    ],
    "https://www.france24.com/fr/": [
        "https://www.france24.com/fr/rss",
    ],
    "https://france3-regions.franceinfo.fr/": [
        "https://france3-regions.franceinfo.fr/rss",
    ],
    "https://www.mediacites.fr/": [
        "https://www.mediacites.fr/feed/",
        "https://www.mediacites.fr/feed/category/municipales-2026/",
        "https://www.mediacites.fr/feed/category/national/",
    ],
    "https://www.lepoint.fr/": [
        "https://www.lepoint.fr/24h-infos/rss.xml",
        "https://www.lepoint.fr/economie/rss.xml",
        "https://www.lepoint.fr/culture/rss.xml",
        "https://www.lepoint.fr/politique/rss.xml",
        "https://www.lepoint.fr/international/rss.xml",
        "https://www.lepoint.fr/sport/rss.xml",
    ],
}



# ============================================================================
# BASE DE DONNÉES
# ============================================================================

class Database:
    """Gestion de la connexion et des opérations MongoDB"""
    
    def __init__(self):
        self.client = MongoClient(Config.MONGO_URI)
        self.db = self.client[Config.MONGO_DB]
        self.articles = self.db["articles"]
        self._create_index()
    
    def _create_index(self):
        """Crée un index unique sur l'URL pour éviter les doublons"""
        try:
            self.articles.create_index("url", unique=True)
        except Exception as e:
            print(f"Warning: Index creation failed - {e}")
    
    def save_article(self, article_data):
        """Sauvegarde un article, retourne True si succès"""
        try:
            self.articles.insert_one(article_data)
            return True
        except errors.DuplicateKeyError:
            return False


# ============================================================================
# CLIENT HTTP
# ============================================================================

class HTTPClient:
    """Client HTTP avec retry et headers appropriés"""
    
    def __init__(self):
        self.session = self._create_session()
    
    def _create_session(self):
        """Crée une session avec retry automatique"""
        session = requests.Session()
        
        # Configuration du retry
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        # Headers
        session.headers.update({
            "User-Agent": Config.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "fr-FR,fr;q=0.9",
        })
        
        return session
    
    def get(self, url):
        """Récupère une page web"""
        try:
            response = self.session.get(url, timeout=Config.TIMEOUT)
            response.raise_for_status()
            return response
        except Exception as e:
            print(f"Erreur HTTP pour {url}: {e}")
            return None


# ============================================================================
# EXTRACTION DE CONTENU
# ============================================================================

class ContentExtractor:
    """Extraction et nettoyage du contenu des articles"""
    
    # Patterns à supprimer du texte
    NOISE_PATTERNS = [
        r"^Temps de lecture.*$",          
        r"^Partager$",                  
        r"^Lire aussi.*$",               
        r"^Publicité$",                 
        r"^Commentaires.*$",             
        r"Ajouter à mes favoris.*$",      
        r"L'article a été ajouté.*$",   
        r"^-\s*$",                       
    ]
    
    def __init__(self, http_client):
        self.http_client = http_client
        self.compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.NOISE_PATTERNS
        ]
    
    def extract_from_url(self, url):
        """Extrait le contenu textuel d'une URL"""
        response = self.http_client.get(url)
        if not response:
            return None
        
        # Extraction avec trafilatura
        text = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
            url=url
        )
        
        if text:
            return self.clean_text(text)
        return None
    
    def extract_from_rss_content(self, html_content, url):
        """Extrait le contenu depuis le HTML du flux RSS"""
        if not html_content:
            return None
        
        text = trafilatura.extract(
            html_content,
            include_comments=False,
            url=url
        )
        
        if text:
            return self.clean_text(text)
        return None
    
    def clean_text(self, text):
        """Nettoie le texte extrait"""
        if not text:
            return text
        
        # Supprime les lignes de bruit
        lines = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            # Vérifie si la ligne correspond à un pattern de bruit
            if any(pattern.search(line) for pattern in self.compiled_patterns):
                continue
            lines.append(line)
        
        # Rejoint et nettoie les espaces multiples
        cleaned = "\n".join(lines)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()


# ============================================================================
# PARSER RSS
# ============================================================================

class RSSParser:
    """Parse les flux RSS et extrait les métadonnées"""
    
    def __init__(self):
        self.cutoff_date = datetime.now(timezone.utc) - timedelta(days=Config.MAX_AGE_DAYS)
    
    def parse_feed(self, rss_url):
        """Parse un flux RSS et retourne les articles récents"""
        try:
            feed = feedparser.parse(rss_url)
            articles = []
            
            for entry in feed.entries[:Config.MAX_PER_FEED]:
                article = self._extract_entry_data(entry, rss_url)
                
                # Filtre par date si disponible
                if article['published_at']:
                    if article['published_at'] < self.cutoff_date:
                        continue
                
                articles.append(article)
            
            return articles
        except Exception as e:
            print(f"Erreur parsing RSS {rss_url}: {e}")
            return []
    
    def _extract_entry_data(self, entry, rss_url):
        """Extrait les données d'une entrée RSS"""
        return {
            'url': entry.get('link', ''),
            'title': entry.get('title', ''),
            'summary': entry.get('summary', ''),
            'content_html': self._get_content_html(entry),
            'published_at': self._parse_date(entry),
            'source_feed': rss_url
        }
    
    def _get_content_html(self, entry):
        """Récupère le contenu HTML d'une entrée RSS"""
        if hasattr(entry, 'content') and entry.content:
            try:
                return entry.content[0].value
            except:
                pass
        return None
    
    def _parse_date(self, entry):
        """Parse la date de publication"""
        for date_field in ('published_parsed', 'updated_parsed'):
            date_tuple = getattr(entry, date_field, None)
            if date_tuple:
                try:
                    timestamp = calendar.timegm(date_tuple)
                    return datetime.fromtimestamp(timestamp, tz=timezone.utc)
                except:
                    pass
        return None


# ============================================================================
# SCRAPER PRINCIPAL
# ============================================================================

class NewsScraper:
    """Orchestrateur principal du scraping"""
    
    def __init__(self):
        self.db = Database()
        self.http_client = HTTPClient()
        self.extractor = ContentExtractor(self.http_client)
        self.rss_parser = RSSParser()
        self.stats = {
            'total': 0,
            'success': 0,
            'too_short': 0,
            'extraction_failed': 0,
            'saved': 0
        }
    
    def scrape_all(self):
        """Lance le scraping de tous les sites"""
        print("=== Début du scraping ===\n")
        
        for site_url, rss_feeds in RSS_SOURCES.items():
            site_domain = self._get_domain(site_url)
            print(f"Traitement de {site_domain}...")
            
            for rss_url in rss_feeds:
                self._scrape_feed(rss_url, site_domain)
                time.sleep(Config.SLEEP_TIME)
        
        self._print_summary()
    
    def _scrape_feed(self, rss_url, site_domain):
        """Scrape un flux RSS spécifique"""
        articles = self.rss_parser.parse_feed(rss_url)
        
        for article in articles:
            self.stats['total'] += 1
            
            try:
                # Tente d'extraire le contenu de la page web
                content = self.extractor.extract_from_url(article['url'])
                
                # Si échec, utilise le contenu RSS
                if not content or len(content) < Config.MIN_CHARS:
                    content = self.extractor.extract_from_rss_content(
                        article['content_html'] or article['summary'],
                        article['url']
                    )
                
                # Vérifie la qualité du contenu
                if not content or len(content) < Config.MIN_CHARS:
                    self.stats['too_short'] += 1
                    continue
                
                # Prépare et sauvegarde l'article
                article_doc = self._create_article_document(
                    article, content, site_domain
                )
                
                if self.db.save_article(article_doc):
                    self.stats['saved'] += 1
                    self.stats['success'] += 1
                else:
                    print(f"  [Doublon] {article['url']}")
                
            except Exception as e:
                self.stats['extraction_failed'] += 1
                print(f"  [Erreur] {article['url']}: {e}")
            
            time.sleep(Config.SLEEP_TIME)
    
    def _create_article_document(self, article, content, site_domain):
        """Crée le document MongoDB pour l'article"""
        return {
            'site': site_domain,
            'url': article['url'],
            'title': article['title'],
            'content': content,
            'published_at': article['published_at'],
            'fetched_at': datetime.now(timezone.utc),
            'metadata': {
                'source_feed': article['source_feed'],
                'content_length': len(content)
            }
        }
    
    def _get_domain(self, url):
        """Extrait le domaine d'une URL"""
        parsed = urlparse(url)
        return parsed.netloc.replace('www.', '')
    
    def _print_summary(self):
        """Affiche le résumé du scraping"""
        print("\n=== Résumé du scraping ===")
        print(f"Articles traités: {self.stats['total']}")
        print(f"Succès: {self.stats['success']}")
        print(f"Sauvegardés: {self.stats['saved']}")
        print(f"Trop courts: {self.stats['too_short']}")
        print(f"Erreurs d'extraction: {self.stats['extraction_failed']}")


# ============================================================================
# POINT D'ENTRÉE
# ============================================================================

def main():
    """Point d'entrée du script"""
    scraper = NewsScraper()
    scraper.scrape_all()


if __name__ == "__main__":
    main()