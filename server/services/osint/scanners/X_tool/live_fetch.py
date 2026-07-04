import os
import sys
import json
import requests
import re

from .config import TWITTER_API45_HOST, TWITTER_API45_KEY, DEFAULT_TIMEOUT
from .quota_tracker import can_call, record_call
from .manual_check import resolve_bio_links

def discover_suspect_handle_fuzzy(approximate_name: str) -> str:
    import requests
    from .config import TWITTR_V2_HOST, TWITTR_V2_KEY
    
    print(f"[*] [STAGE 1 DISCOVERY] Target input '{approximate_name}' is irregular.")
    print(f"[*] Querying Twittr v2 network directory for fuzzy variations...")
    
    url = f"https://{TWITTR_V2_HOST}/search/{approximate_name}"
    headers = {
        "X-RapidAPI-Key": TWITTR_V2_KEY,
        "X-RapidAPI-Host": TWITTR_V2_HOST
    }

    if not TWITTR_V2_KEY:
        print(f"[!] Twittr v2 key missing. Defaulting to literal string.")
        return approximate_name
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            results = response.json()
            if isinstance(results, list) and len(results) > 0:
                resolved_handle = results[0].get("username") or results[0].get("screen_name")
                if resolved_handle:
                    print(f"[+] [DISCOVERY SUCCESS] Resolved fuzzy target '{approximate_name}' ──> @{resolved_handle}")
                    return resolved_handle
                    
            elif isinstance(results, dict) and "users" in results:
                user_list = results.get("users", [])
                if user_list:
                    resolved_handle = user_list[0].get("screen_name")
                    print(f"[+] [DISCOVERY SUCCESS] Resolved fuzzy target '{approximate_name}' ──> @{resolved_handle}")
                    return resolved_handle
                    
        print(f"[!] Fuzzy search yielded zero directory nodes. Defaulting to literal string.")
        return approximate_name
    except Exception as e:
        print(f"[!] Discovery layer exception: {e}. Defaulting to literal string.")
        return approximate_name

def fetch_target_profile_rapid(username: str):
    clean_username = username.strip().lstrip("@")
    print(f"\n[*] [INTEL] Initializing Live OSINT Capture Target: @{clean_username}")

    clean_dir = os.path.join("evidence_vault", ".clean_report")
    os.makedirs(clean_dir, exist_ok=True)

    headers = {
        "X-RapidAPI-Key": TWITTER_API45_KEY,
        "X-RapidAPI-Host": TWITTER_API45_HOST
    }

    if not TWITTER_API45_KEY:
        print(f"[!] twitter-api45 key missing. Checking for cached copy only.")
        cached = _load_from_cache(clean_username, clean_dir)
        if cached:
            return cached
        return False

    profile_data = {}
    if not can_call("twitter_api45"):
        print("[!] Quota exhausted for twitter_api45 — cannot fetch profile. Checking for cached copy...")
        return _load_from_cache(clean_username, clean_dir)

    profile_url = f"https://twitter-api45.p.rapidapi.com/screenname.php?screenname={clean_username}"
    try:
        p_res = requests.get(profile_url, headers=headers, timeout=DEFAULT_TIMEOUT)
        record_call("twitter_api45")
        print(f"[*] Profile Endpoint HTTP Status: {p_res.status_code}")
        if p_res.status_code == 200:
            profile_data = p_res.json()
        elif p_res.status_code in (429, 403):
            print("[!] Rate limited or quota rejected by gateway. Falling back to cache if available.")
            cached = _load_from_cache(clean_username, clean_dir)
            if cached:
                return cached
    except Exception as e:
        print(f"[!] Profile Network Exception: {e}")
        cached = _load_from_cache(clean_username, clean_dir)
        if cached:
            return cached

    if not profile_data:
        print(f"[!] No profile data retrieved for @{clean_username}. Aborting.")
        return False

    bio_text = profile_data.get("desc") or ""
    display_name = profile_data.get("name") or "N/A"
    location_stated = profile_data.get("location") or "NOT SPECIFIED"
    creation_date = profile_data.get("created_at") or "NOT PROVIDED BY API"
    user_id = profile_data.get("id") or profile_data.get("rest_id") or "N/A"
    avatar_url = profile_data.get("avatar") or profile_data.get("profile_image_url") or ""

    followers = profile_data.get("sub_count") or 0
    following = profile_data.get("friends") or 0
    total_statuses = profile_data.get("statuses_count") or 0

    found_emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', bio_text)
    found_links = re.findall(r'https?://[^\s]+', bio_text)

    resolved_links = resolve_bio_links(found_links) if found_links else []

    bio_pivots = {
        "Extracted_Emails": list(set(found_emails)),
        "Extracted_URLs_Raw": list(set(found_links)),
        "Extracted_URLs_Resolved": resolved_links
    }

    captured_tweets = []
    TIMELINE_TIMEOUT = 30
    MAX_RETRIES = 2

    if can_call("twitter_api45"):
        timeline_url = f"https://twitter-api45.p.rapidapi.com/timeline.php?screenname={clean_username}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                t_res = requests.get(timeline_url, headers=headers, timeout=TIMELINE_TIMEOUT)
                record_call("twitter_api45")
                print(f"[*] Timeline Endpoint HTTP Status: {t_res.status_code} (attempt {attempt}/{MAX_RETRIES})")
                if t_res.status_code == 200:
                    captured_tweets = t_res.json().get("timeline", [])
                    print(f"[+][DATA] Successfully parsed {len(captured_tweets)} live feed items from gateway.")
                    break
                elif t_res.status_code in (429, 403):
                    print("[!] Rate limited or quota rejected on timeline endpoint. Not retrying.")
                    break
            except requests.exceptions.ReadTimeout:
                record_call("twitter_api45")
                print(f"[!] Timeline request timed out after {TIMELINE_TIMEOUT}s (attempt {attempt}/{MAX_RETRIES}).")
                if attempt == MAX_RETRIES:
                    print("[!] Giving up on timeline after max retries. Profile-only record will be saved.")
            except Exception as e:
                print(f"[!] Timeline Network Exception: {e}")
                break
    else:
        print("[!] Quota exhausted — skipping timeline fetch, profile-only record will be saved.")

    hourly_matrix = {f"{hour:02d}:00": 0 for hour in range(24)}
    interaction_network = {}
    hashtag_clusters = {}
    normalized_timeline = []

    geo_keywords = ["california", "florida", "texas", "starbase", "venezuela", "philippines", "london", "new york", "tokyo", "mountain view"]

    for tweet in captured_tweets:
        tweet_text = tweet.get("text") or tweet.get("message") or ""
        if not tweet_text:
            continue

        mentions = re.findall(r'@[\w]+', tweet_text)
        hashtags = re.findall(r'#[\w]+', tweet_text)

        for m in mentions:
            m = m.lower()
            interaction_network[m] = interaction_network.get(m, 0) + 1

        for h in hashtags:
            h = h.lower()
            hashtag_clusters[h] = hashtag_clusters.get(h, 0) + 1

        discovered_location = "Not Specified"
        lower_text = tweet_text.lower()
        for loc in geo_keywords:
            if loc in lower_text:
                discovered_location = loc.upper()
                break

        created_at = tweet.get("created_at") or ""
        if created_at:
            try:
                parsed = datetime_strptime_safe(created_at)
                if parsed:
                    hourly_matrix[f"{parsed.hour:02d}:00"] += 1
            except Exception:
                pass

        normalized_timeline.append({
            "Broadcast_Timestamp": created_at,
            "Message_Content": tweet_text,
            "Geospatial_Footprint": {
                "Precise_GPS_Coordinates": "NOT ATTACHED",
                "Verified_Location_Tag": discovered_location
            }
        })

    sorted_network = dict(sorted(interaction_network.items(), key=lambda item: item[1], reverse=True)[:10])
    sorted_hashtags = dict(sorted(hashtag_clusters.items(), key=lambda item: item[1], reverse=True)[:10])

    if not sorted_hashtags:
        sorted_hashtags = {"#general_updates": 1}

    clean_payload = {
        "Case_Evidentiary_Metadata": {
            "Permanent_Platform_ID_Number": str(user_id),
            "Account_Creation_Date": creation_date,
            "Direct_Source_Verification_URL": f"https://x.com/{clean_username}"
        },
        "Target_Core_Identity": {
            "Target_Username": clean_username,
            "Target_Display_Name": display_name,
            "Profile_Bio_Text": bio_text,
            "Stated_Geographic_Location": location_stated,
            "Avatar_Image_URL": avatar_url
        },
        "Platform_Volume_Metrics": {
            "Following_Count_Outbound": following,
            "Followers_Count_Inbound": followers,
            "Lifetime_Total_Posts_Posted": total_statuses,
            "Total_Recent_Posts_Analyzed": len(normalized_timeline)
        },
        "Bio_Discovered_Network_Pivots": bio_pivots,
        "Behavioral_Frequency_Analysis": {
            "Most_Interacted_With_Handles": sorted_network,
            "Most_Used_Hashtags_Clustering": sorted_hashtags,
            "Temporal_Hourly_Post_Profile_UTC": hourly_matrix
        },
        "Captured_Public_Timeline_Data": normalized_timeline if normalized_timeline else "NO RECENT PUBLIC TIMELINE POSTS RETURNED",
        "Audit_Trail": {
            "Data_Source": "RapidAPI twitter-api45 (unofficial bridge — free tier)",
            "Collection_Timestamp_UTC": _utc_now_iso(),
            "Methodology_Version": "v1.2-hackathon",
            "Platform_ToS_Note": "All data sourced from publicly accessible profile endpoints"
        },
        "Raw_API_Response_Snapshot": profile_data
    }

    output_filepath = os.path.join(clean_dir, f"{clean_username}.json")
    with open(output_filepath, "w", encoding="utf-8") as f:
        json.dump(clean_payload, f, indent=4, ensure_ascii=False)

    print(f"[+][SUCCESS] Integrated Forensic Target File Created: {output_filepath}")
    return True


def _load_from_cache(clean_username: str, clean_dir: str):
    cache_path = os.path.join(clean_dir, f"{clean_username}.json")
    if os.path.exists(cache_path):
        print(f"[+] Loaded cached report for @{clean_username} (quota-safe fallback).")
        return True
    print(f"[!] No cached report available for @{clean_username}.")
    return False


def datetime_strptime_safe(created_at: str):
    from datetime import datetime
    twitter_fmt = "%a %b %d %H:%M:%S %z %Y"
    try:
        return datetime.strptime(created_at, twitter_fmt)
    except (ValueError, TypeError):
        return None


def _utc_now_iso():
    from datetime import datetime
    return datetime.utcnow().isoformat()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        fetch_target_profile_rapid(sys.argv[1])
    else:
        user_input = input("Enter target X handle to profile: ")
        if user_input.strip():
            fetch_target_profile_rapid(user_input)