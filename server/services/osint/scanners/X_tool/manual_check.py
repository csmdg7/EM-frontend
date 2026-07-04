import requests
import json
from .config import TWITTER_API45_HOST, TWITTER_API45_KEY

def check_follow_relationship(user_a: str, user_b: str) -> bool:
    user_a = user_a.strip().lstrip("@")
    user_b = user_b.strip().lstrip("@")
    
    url = f"https://{TWITTER_API45_HOST}/checkfollow.php"
    
    headers = {
        "X-RapidAPI-Key": TWITTER_API45_KEY,
        "X-RapidAPI-Host": TWITTER_API45_HOST,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    params = {
        "screenname": user_a,
        "target": user_b
    }
    
    try:
        from .quota_tracker import record_call, can_call
        if not TWITTER_API45_KEY:
            return _execute_algorithmic_fallback(user_a, user_b)
        if not can_call("twitter_api45"):
            return _execute_algorithmic_fallback(user_a, user_b)
            
        response = requests.get(url, headers=headers, params=params, timeout=12)
        record_call("twitter_api45")
        
        if response.status_code == 200:
            response_text = response.text.strip()
            if not response_text:
                print(f"[!] Primary bridge returned empty string. Engaging algorithmic fallback layer...")
                return _execute_algorithmic_fallback(user_a, user_b)
                
            try:
                data = response.json()
                is_following = data.get("following", False)
                is_followed_by = data.get("followed_by", False)
                return bool(is_following or is_followed_by)
            except ValueError:
                return _execute_algorithmic_fallback(user_a, user_b)
                
        return _execute_algorithmic_fallback(user_a, user_b)
    except Exception:
        return _execute_algorithmic_fallback(user_a, user_b)

def _execute_algorithmic_fallback(user_a: str, user_b: str) -> bool:
    import os
    vault_path = "evidence_vault/.clean_report"
    file_a = os.path.join(vault_path, f"{user_a}.json")
    file_b = os.path.join(vault_path, f"{user_b}.json")
    
    if os.path.exists(file_a) and os.path.exists(file_b):
        try:
            with open(file_a, "r", encoding="utf-8") as f:
                data_a = json.load(f)
            with open(file_b, "r", encoding="utf-8") as f:
                data_b = json.load(f)
                
            mentions_a = data_a.get("Behavioral_Frequency_Analysis", {}).get("Most_Interacted_With_Handles", {})
            mentions_b = data_b.get("Behavioral_Frequency_Analysis", {}).get("Most_Interacted_With_Handles", {})
            
            if user_b.lower() in [m.lower() for m in mentions_a.keys()] or \
               user_a.lower() in [m.lower() for m in mentions_b.keys()]:
                print(f"[+] Fallback Linkage Verified: Structural behavioral interactions discovered.")
                return True
        except Exception:
            pass
            
    return False

def resolve_bio_links(links_list: list) -> list:
    return links_list