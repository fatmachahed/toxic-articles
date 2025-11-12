import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI","mongodb://localhost:27017")
MONGO_DB  = os.getenv("MONGO_DB","toxic_news")

_client = AsyncIOMotorClient(MONGO_URI)
db = _client[MONGO_DB]

# Créer 3 collections 
articles        = db["articles"]    
predictions     = db["predictions"]
toxicity_stats  = db["statistics"]
