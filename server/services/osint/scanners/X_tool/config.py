import os
from dotenv import load_dotenv
from server.services.osint.scanners.shared import RAPIDAPI_API_KEY

load_dotenv()

# Two RapidAPI providers now in play
TWITTER_API45_HOST = "twitter-api45.p.rapidapi.com"
TWITTR_V2_HOST = "twittr-v2-fastest-twitter-x-api-150k-requests-for-15.p.rapidapi.com"

TWITTER_API45_KEY = os.getenv("TWITTER_API45_KEY", "") or RAPIDAPI_API_KEY
TWITTR_V2_KEY = os.getenv("TWITTR_V2_KEY", "") or RAPIDAPI_API_KEY

DEFAULT_TIMEOUT = 15

# Global Framework Directory Structuring Maps
VAULT_DIR = "evidence_vault"
CLEAN_REPORT_DIR = os.path.join(VAULT_DIR, ".clean_report")
FRONTEND_ASSET_DIR = os.path.join(VAULT_DIR, "front_end_assets")
QUOTA_FILE = os.path.join(VAULT_DIR, ".quota_tracker.json")

# Free-tier caps — adjust to match your actual plan per key
QUOTA_LIMITS = {
    "twitter_api45": 500,
    "twittr_v2": 500
}