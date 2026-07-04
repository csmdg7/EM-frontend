"""
server/services/osint/scanners/instagram.py
===========================================
Instagram OSINT scanner via HikerAPI + Flash API (RapidAPI).

APIs used:
  - HikerAPI: api.hikerapi.com (requires HIKERAPI_KEY)
  - Flash API: flashapi1.p.rapidapi.com (requires FLASHAPI_KEY)

Exports:
    scan_instagram(code, username) -> None
    fetch_instagram(username)      -> dict   (raw data, no storage write)
"""

print("[ECHOMARK][scanners/instagram.py] Module loaded — Instagram scanner initializing")

import os
import re
import json
import requests
from datetime import datetime
from server.storage.cases import upsert_section
from server.services.osint.scanners.shared import RAPIDAPI_API_KEY, _log

# Env keys (add to .env: HIKERAPI_KEY, FLASHAPI_KEY)
HIKERAPI_KEY = os.environ.get("HIKERAPI_KEY", "")
FLASHAPI_KEY = os.environ.get("FLASHAPI_KEY", RAPIDAPI_API_KEY)  # fallback to existing key

HIKER_BASE = "https://api.hikerapi.com"
HIKER_HEADERS = {"x-access-key": HIKERAPI_KEY, "accept": "application/json"}
FLASH_HEADERS = {
    "x-rapidapi-key": FLASHAPI_KEY,
    "x-rapidapi-host": "flashapi1.p.rapidapi.com",
    "Content-Type": "application/json"
}


def _parse_flash_media(items):
    """Extract post/reel URLs, thumbnails, video URLs, timestamps, captions.
    HikerAPI /v1/user/medias returns media objects directly (not wrapped in 'media' key)."""
    results = []
    seen = set()
    for media in items:
        code = media.get("code", "")
        if not code or code in seen:
            continue
        seen.add(code)

        is_reel = media.get("product_type", "") == "clips"
        taken_at_raw = media.get("taken_at", 0)
        # Handle both string and int timestamps
        try:
            taken_at_ts = int(taken_at_raw)
        except (ValueError, TypeError):
            taken_at_ts = 0

        thumb = ""
        candidates = media.get("image_versions2", {}).get("candidates", [])
        if candidates:
            thumb = candidates[0].get("url", "")

        video_url = ""
        if is_reel:
            vv = media.get("video_versions", [])
            if vv:
                video_url = vv[0].get("url", "")

        cap_obj = media.get("caption")
        cap_text = cap_obj.get("text", "") if isinstance(cap_obj, dict) else ""

        results.append({
            "post_url": f"https://www.instagram.com/{'reel' if is_reel else 'p'}/{code}/",
            "thumbnail_url": thumb,
            "video_url": video_url,
            "posted_at": datetime.fromtimestamp(taken_at_ts).strftime("%d %b %Y, %I:%M %p") if taken_at_ts else "unknown",
            "taken_at_ts": taken_at_ts,
            "caption": cap_text,
        })
    return results


# ---------- Fake account scoring (ported from upstream) ----------
def _analyze_username_pattern(username):
    reasons = []
    score = 0
    num_count = sum(c.isdigit() for c in username)
    if num_count >= 4:
        score += 1
        reasons.append(f"Username contains {num_count} numbers (possible auto-generated)")
    if username.startswith("_") or username.endswith("_"):
        score += 0.5
        reasons.append("Username starts/ends with underscore")
    if len(username) > 20:
        score += 0.5
        reasons.append("Unusually long username")
    if re.search(r'[a-z]{1,3}\d{3,}', username.lower()):
        score += 1
        reasons.append("Username pattern looks auto-generated (letters + number block)")
    return score, reasons


def _analyze_captions(captions):
    reasons = []
    score = 0
    if not captions:
        return score, reasons
    for cap in captions:
        hc = len(re.findall(r'#\w+', cap))
        if hc >= 15:
            score += 1
            reasons.append(f"Hashtag stuffing detected ({hc} hashtags in one post)")
            break
    if len(captions) > 2:
        uniq = len(set(captions)) / len(captions)
        if uniq < 0.6:
            score += 1.5
            reasons.append("Repeated/duplicate captions across posts")
    return score, reasons


def _get_sample_confidence(sampled, total):
    if total == 0:
        return 0
    ratio = sampled / total
    if ratio >= 0.5:
        return 1.0
    elif ratio >= 0.2:
        return 0.7
    elif ratio >= 0.05:
        return 0.4
    return 0.2


def _analyze_caption_quality(captions):
    score = 0
    reasons = []
    if not captions:
        return score, reasons

    avg_len = sum(len(c) for c in captions) / len(captions)
    if avg_len < 5:
        score += 1
        reasons.append("Captions are extremely short on average")

    all_caps = sum(1 for c in captions if c.upper() == c and len(c) > 5)
    if all_caps / len(captions) > 0.5:
        score += 1
        reasons.append(f"{int(all_caps/len(captions)*100)}% of captions are all-caps")

    import unicodedata
    def is_emoji(ch):
        return unicodedata.category(ch) in ('So', 'Sm')

    emoji_heavy = 0
    for cap in captions:
        tc = len(cap.replace(" ", ""))
        if tc == 0:
            continue
        ec = sum(1 for ch in cap if is_emoji(ch))
        if tc > 0 and ec / tc > 0.5:
            emoji_heavy += 1
    if captions and emoji_heavy / len(captions) > 0.5:
        score += 0.5
        reasons.append("Most captions are emoji-only (no real text content)")

    spam_kw = ["follow", "followback", "follow4follow", "f4f", "like4like", "l4l",
               "dm for promo", "link in bio", "giveaway", "win free"]
    spam_hits = sum(1 for cap in captions if any(kw in cap.lower() for kw in spam_kw))
    if spam_hits:
        score += spam_hits * 0.5
        reasons.append(f"{spam_hits} captions contain spam/promotional keywords")
    return score, reasons


def _analyze_posting_hours(medias):
    score = 0
    reasons = []
    hours = []
    for m in medias:
        ts = m.get("taken_at_ts", 0)
        if ts:
            try:
                hours.append(datetime.fromtimestamp(ts).hour)
            except Exception:
                pass
    if len(hours) < 3:
        return score, reasons

    uniq = set(hours)
    if len(uniq) == 1:
        score += 1.5
        reasons.append(f"All posts published at exactly hour {hours[0]}:00 — robotic scheduling")
    elif len(uniq) <= 2:
        score += 1
        reasons.append("Posts clustered in very narrow time window")

    sus = sum(1 for h in hours if 2 <= h <= 5)
    if sus / len(hours) > 0.7:
        score += 1
        reasons.append("Majority of posts published between 2-5am (bot-typical hours)")
    return score, reasons


def _analyze_follower_quality(followers, following, total_followers=0):
    reasons = []
    score = 0
    if not followers and not following:
        return score, reasons

    if followers:
        total = len(followers)
        no_pic = gen_user = private_cnt = verified_cnt = 0
        for f in followers:
            uname = f.get("username", "")
            has_pic = f.get("profile_pic_url") not in [None, ""]
            is_private = f.get("is_private", False)
            is_verified = f.get("is_verified", False)
            if not has_pic:
                no_pic += 1
            if sum(c.isdigit() for c in uname) >= 4:
                gen_user += 1
            if is_private:
                private_cnt += 1
            if is_verified:
                verified_cnt += 1

        no_pic_ratio = no_pic / total
        gen_ratio = gen_user / total
        priv_ratio = private_cnt / total
        ver_ratio = verified_cnt / total

        if no_pic_ratio > 0.5:
            score += 2
            reasons.append(f"{int(no_pic_ratio*100)}% of followers have no profile picture (bot signal)")
        elif no_pic_ratio > 0.3:
            score += 1
            reasons.append(f"{int(no_pic_ratio*100)}% of followers have no profile picture")

        if gen_ratio > 0.4:
            score += 2
            reasons.append(f"{int(gen_ratio*100)}% of followers have auto-generated usernames")
        elif gen_ratio > 0.2:
            score += 1
            reasons.append(f"{int(gen_ratio*100)}% of followers have suspicious usernames")

        if priv_ratio > 0.8:
            score += 1
            reasons.append(f"{int(priv_ratio*100)}% of followers are private accounts (unusual)")

        if ver_ratio > 0.1:
            score -= 1
            reasons.append(f"{int(ver_ratio*100)}% of followers are verified (credibility signal)")

    if following:
        total_fg = len(following)
        gen_fg = sum(1 for f in following if sum(c.isdigit() for c in f.get("username", "")) >= 4)
        gen_fg_ratio = gen_fg / total_fg
        if gen_fg_ratio > 0.4:
            score += 1.5
            reasons.append(f"{int(gen_fg_ratio*100)}% of following accounts have bot-like usernames")

    if followers and following:
        f_ids = set(f.get("pk", f.get("id", "")) for f in followers)
        fg_ids = set(f.get("pk", f.get("id", "")) for f in following)
        overlap = f_ids & fg_ids
        overlap_ratio = len(overlap) / max(len(f_ids), 1)
        if overlap_ratio > 0.7:
            score += 2
            reasons.append(f"{int(overlap_ratio*100)}% overlap between followers/following ({len(overlap)} accounts) — possible mutual follow farm")
        elif overlap_ratio > 0.4:
            score += 1
            reasons.append(f"{int(overlap_ratio*100)}% overlap between followers and following")

    conf = _get_sample_confidence(len(followers), total_followers)
    score *= conf
    if conf < 0.5:
        reasons.append(f"Note: follower analysis based on {len(followers)} sampled out of {total_followers} total — low sample confidence")
    return score, reasons


def _fake_account_score(profile, medias=None, followers=None, following=None, captions=None):
    total_score = 0
    all_reasons = []
    medias = medias or []
    followers = followers or []
    following = following or []
    captions = captions or []

    fc = profile.get("follower_count", 0)
    fgc = profile.get("following_count", 0)
    pc = profile.get("post_count", profile.get("media_count", 0))
    uname = profile.get("username", "")

    if pc == 0:
        total_score += 1.5
        all_reasons.append("Account has zero posts")
    if not profile.get("bio", profile.get("biography", "")).strip():
        total_score += 0.5
        all_reasons.append("Empty bio")
    if not profile.get("full_name", "").strip():
        total_score += 0.5
        all_reasons.append("No full name set")
    if not profile.get("profile_pic_url"):
        total_score += 1
        all_reasons.append("No profile picture set")

    if fc > 0:
        ratio = fgc / max(fc, 1)
        if ratio > 10:
            total_score += 2
            all_reasons.append(f"Following/follower ratio extremely high ({ratio:.1f}x)")
        elif ratio > 5:
            total_score += 1
            all_reasons.append(f"Following far more than followers (ratio {ratio:.1f}x)")
    elif fgc > 500 and fc == 0:
        total_score += 2
        all_reasons.append("Following many accounts with zero followers")

    if medias and fc > 1000:
        avg_likes = sum(m.get("like_count", 0) for m in medias) / len(medias)
        er = avg_likes / fc
        if er < 0.001:
            total_score += 2
            all_reasons.append(f"Extremely low engagement ({er*100:.3f}%)")
        elif er < 0.005:
            total_score += 1
            all_reasons.append(f"Low engagement rate ({er*100:.2f}%)")

    u_s, u_r = _analyze_username_pattern(uname)
    total_score += u_s
    all_reasons.extend(u_r)

    if not captions and medias:
        captions = [m.get("caption_text", "") for m in medias if m.get("caption_text")]

    c_s, c_r = _analyze_captions(captions)
    total_score += c_s
    all_reasons.extend(c_r)

    cq_s, cq_r = _analyze_caption_quality(captions)
    total_score += cq_s
    all_reasons.extend(cq_r)

    ph_s, ph_r = _analyze_posting_hours(medias)
    total_score += ph_s
    all_reasons.extend(ph_r)

    fq_s, fq_r = _analyze_follower_quality(followers, following, fc)
    total_score += fq_s
    all_reasons.extend(fq_r)

    max_possible = 18
    normalized = min(max(round((total_score / max_possible) * 100), 0), 100)

    if normalized >= 70:
        label = "HIGH RISK — Likely fake or bot account"
    elif normalized >= 40:
        label = "MEDIUM RISK — Suspicious, needs further investigation"
    elif normalized >= 20:
        label = "LOW RISK — Some anomalies detected"
    else:
        label = "LIKELY GENUINE"

    return {
        "fake_score_percent": normalized,
        "verdict": label,
        "signals_triggered": len(all_reasons),
        "reasons": all_reasons,
    }


# ---------- Public API ----------
def fetch_instagram(username: str) -> dict:
    """
    Full investigation via HikerAPI + Flash API.
    Returns a cleaned dict or {"error": "..."} on failure.
    """
    print(f"[ECHOMARK][scanners/instagram.py] fetch_instagram: querying '{username}'")

    if not HIKERAPI_KEY:
        return {"error": "HIKERAPI_KEY not configured"}
    if not FLASHAPI_KEY:
        return {"error": "FLASHAPI_KEY not configured"}

    try:
        # 1. Profile
        r = requests.get(f"{HIKER_BASE}/v1/user/by/username",
                         params={"username": username}, headers=HIKER_HEADERS, timeout=15)
        r.raise_for_status()
        hp = r.json()
        user_id = hp["pk"]
        is_private = hp.get("is_private", False)

        result = {
            "username": hp["username"],
            "user_id": user_id,
            "full_name": hp.get("full_name", ""),
            "bio": hp.get("biography", ""),
            "profile_pic_url": hp.get("profile_pic_url_hd") or hp.get("profile_pic_url", ""),
            "follower_count": hp.get("follower_count", 0),
            "following_count": hp.get("following_count", 0),
            "post_count": hp.get("media_count", 0),
            "is_private": is_private,
            "is_verified": hp.get("is_verified", False),
            "account_details": {"country": "", "joined_date": "", "former_usernames_count": ""},
            "captions": [],
            "media_urls": [],
            "followers": [],
            "following": [],
            "similar_accounts": [],
            "fake_account_analysis": None,
        }

        # 2. Account about (creation date, country, former usernames)
        try:
            about = requests.get(f"{HIKER_BASE}/gql/user/about",
                                 params={"id": user_id}, headers=HIKER_HEADERS, timeout=10).json()
            result["account_details"] = {
                "country": about.get("country", ""),
                "joined_date": about.get("date", ""),
                "former_usernames_count": about.get("former_usernames", ""),
                "is_verified": about.get("is_verified", False),
            }
        except Exception as e:
            print(f"[ECHOMARK][scanners/instagram.py] fetch_instagram: about fetch failed — {e}")

        medias = []

        if is_private:
            print("[ECHOMARK][scanners/instagram.py] fetch_instagram: private account — limited data")
            try:
                sim = requests.get("https://flashapi1.p.rapidapi.com/ig/similar_accounts/",
                                   params={"id_user": user_id}, headers=FLASH_HEADERS, timeout=10).json()
                result["similar_accounts"] = list(dict.fromkeys(
                    item.get("username", "") for item in sim if item.get("username")
                ))
            except Exception as e:
                print(f"[ECHOMARK][scanners/instagram.py] fetch_instagram: similar accounts failed — {e}")
        else:
            # 3. Posts / media
            try:
                medias = requests.get(f"{HIKER_BASE}/v1/user/medias",
                                      params={"user_id": user_id}, headers=HIKER_HEADERS, timeout=15).json()
                result["media_urls"] = _parse_flash_media(medias)

                seen_caps = set()
                for m in medias:
                    cap = m.get("caption_text", "").strip()
                    if cap and cap not in seen_caps:
                        seen_caps.add(cap)
                        result["captions"].append(cap)
            except Exception as e:
                print(f"[ECHOMARK][scanners/instagram.py] fetch_instagram: medias failed — {e}")

            # 4. Followers
            try:
                raw_followers = []
                max_id = None
                for _ in range(5):  # max_pages
                    fr = requests.get(f"{HIKER_BASE}/v1/user/followers/chunk",
                                      params={"user_id": user_id, "max_id": max_id},
                                      headers=HIKER_HEADERS, timeout=10).json()
                    # Handle both dict {"users": [...], "next_max_id": "..."} and direct list [...]
                    if isinstance(fr, list):
                        users = fr
                        max_id = None
                    else:
                        users = fr.get("users", [])
                        max_id = fr.get("next_max_id")
                    raw_followers.extend(users)
                    if not max_id:
                        break
                result["followers"] = list(dict.fromkeys(
                    u.get("username") for u in raw_followers if u.get("username")
                ))
            except Exception as e:
                print(f"[ECHOMARK][scanners/instagram.py] fetch_instagram: followers failed — {e}")

            # 5. Following
            try:
                raw_following = []
                max_id = None
                for _ in range(5):
                    fr = requests.get(f"{HIKER_BASE}/v1/user/following/chunk",
                                      params={"user_id": user_id, "max_id": max_id},
                                      headers=HIKER_HEADERS, timeout=10).json()
                    if isinstance(fr, list):
                        users = fr
                        max_id = None
                    else:
                        users = fr.get("users", [])
                        max_id = fr.get("next_max_id")
                    raw_following.extend(users)
                    if not max_id:
                        break
                result["following"] = list(dict.fromkeys(
                    u.get("username") for u in raw_following if u.get("username")
                ))
            except Exception as e:
                print(f"[ECHOMARK][scanners/instagram.py] fetch_instagram: following failed — {e}")

        # 6. Fake account scoring
        result["fake_account_analysis"] = _fake_account_score(
            result, medias, result["followers"], result["following"]
        )

        print(f"[ECHOMARK][scanners/instagram.py] fetch_instagram: OK — followers={result['follower_count']}")
        return result

    except Exception as e:
        print(f"[ECHOMARK][scanners/instagram.py] fetch_instagram: error — {e}")
        return {"error": str(e)}


def scan_instagram(code: str, username: str) -> None:
    """
    Full Instagram pipeline for a case.
    Writes sections: instagram, gallery, followers, sentiment, fake_account, related_platforms.
    """
    print(f"[ECHOMARK][scanners/instagram.py] scan_instagram: START code={code} username='{username}'")
    _log(code, f"[INSTAGRAM] Scan started for '{username}'")

    data = fetch_instagram(username)

    if "error" in data:
        upsert_section(code, "instagram", {"section": "instagram", "query": username, "error": data["error"]})
        _log(code, f"[INSTAGRAM] Error: {data['error']}")
    else:
        # 1. instagram — core profile + profile pic for the right-side image div
        upsert_section(code, "instagram", {
            "section":         "instagram",
            "query":           username,
            "username":        data.get("username", ""),
            "full_name":       data.get("full_name", ""),
            "bio":             data.get("bio", ""),
            "follower_count":  data.get("follower_count", 0),
            "following_count": data.get("following_count", 0),
            "post_count":      data.get("post_count", 0),
            "is_private":      data.get("is_private", False),
            "is_verified":     data.get("is_verified", False),
            "profile_pic_url": data.get("profile_pic_url", ""),
            "account_details": data.get("account_details", {}),
        })

        # 2. gallery — images list with {url} dicts (matches renderGallery)
        upsert_section(code, "gallery", {
            "section": "gallery",
            "query":   username,
            "images":  [{"url": m["thumbnail_url"]} for m in data.get("media_urls", []) if m.get("thumbnail_url")],
        })

        # 3. media_intelligence — full post objects
        upsert_section(code, "media_intelligence", {
            "section": "media_intelligence",
            "query":   username,
            "media":   data.get("media_urls", []),
        })

        # 4. followers — ONE section with both followers AND following keys (matches renderFollowers)
        upsert_section(code, "followers", {
            "section":   "followers",
            "query":     username,
            "followers": data.get("followers", []),
            "following": data.get("following", []),
            "friends":   [],
        })

        # 5. sentiment — flat keys matching renderSentiment expectations
        captions = data.get("captions", [])
        spam_kw = ["follow", "followback", "follow4follow", "f4f", "like4like",
                   "dm for promo", "link in bio", "giveaway", "win free"]
        keyword_hits = [kw for kw in spam_kw if any(kw in c.lower() for c in captions)]
        upsert_section(code, "sentiment", {
            "section":          "sentiment",
            "query":            username,
            "behavior_score":   0,
            "extracted_bio":    data.get("bio", ""),
            "keywords":         keyword_hits,
            "captions":         captions[:20],
            "behavior_verdict": f"{len(captions)} caption(s) analyzed." if captions else "No caption data.",
        })

        # 6. fake_account — keys matching renderFakeAccount (verdict/confidence/indicators)
        fa = data.get("fake_account_analysis") or {}
        upsert_section(code, "fake_account", {
            "section":    "fake_account",
            "query":      username,
            "verdict":    fa.get("verdict", "Pending"),
            "confidence": fa.get("fake_score_percent", 0),
            "indicators": fa.get("reasons", []),
            "note":       f"{fa.get('signals_triggered', 0)} signal(s) triggered.",
        })

        _log(code, "[INSTAGRAM] Core sections written")

    # Related platforms via Sherlock
    from server.services.osint.scanners.sherlock import run_sherlock
    sherlock_results = run_sherlock(username)
    upsert_section(code, "related_platforms", {
        "section":   "related_platforms",
        "query":     username,
        "platforms": sherlock_results,
        "source":    "sherlock",
    })
    _log(code, f"[INSTAGRAM] Related platforms: {len(sherlock_results)} via Sherlock")
    _log(code, "[INSTAGRAM] All sections written")
    print(f"[ECHOMARK][scanners/instagram.py] scan_instagram: END code={code}")


print("[ECHOMARK][scanners/instagram.py] Module ready — fetch_instagram, scan_instagram exported")