import os
import sys
import json

from .live_fetch import fetch_target_profile_rapid, discover_suspect_handle_fuzzy
from .confidence_scorer import ForensicLinkageScorer
from .manual_check import check_follow_relationship
from .quota_tracker import remaining

CLEAN_REPORT_DIR = os.path.join("evidence_vault", ".clean_report")


def main():
    print("======================================================")
    print("    OSINT CROSS-PROFILE LINKAGE ANALYTICS WORKSTATION  ")
    print("======================================================\n")

    args = sys.argv[1:]

    if len(args) == 0:
        primary = input("Enter primary subject handle: ").strip()
        if not primary:
            print("[!] Error: A primary target handle is required.")
            return
        secondary = input("Enter secondary verification handle (Leave blank for single profile scan): ").strip()
    elif len(args) == 1:
        primary = args[0]
        secondary = ""
    else:
        primary = args[0]
        secondary = args[1]

    raw_target_a = primary.lstrip("@")
    raw_target_b = secondary.lstrip("@") if secondary else ""

    # Surface remaining quota up front so you know how many live runs you have left
    print(f"[*] Quota remaining — twitter_api45: {remaining('twitter_api45')} | twittr_v2: {remaining('twittr_v2')}\n")

    # Step 1: Execute Stage 1 Fuzzy Resolution Discovery for Primary Target
    print(f"[*] Analyzing target string pattern for Phase 1: @{raw_target_a}")
    target_a = discover_suspect_handle_fuzzy(raw_target_a)

    # Step 2: Process Primary Target Ingestion
    print(f"[*] Launching phase 1 investigation on resolved handle: @{target_a}")
    success_a = fetch_target_profile_rapid(target_a)

    if not success_a:
        print(f"[!] Critical Failure: Unable to parse target profile [@{target_a}]. Pipeline stopped.")
        return

    profile_a_path = os.path.join(CLEAN_REPORT_DIR, f"{target_a}.json")
    with open(profile_a_path, "r", encoding="utf-8") as f:
        profile_a = json.load(f)

    # Step 3: Single Profile Scan
    if not raw_target_b:
        print("\n" + "=" * 50)
        print(f"📊 ACTIONABLE INTELLIGENCE DOSSIER SUMMARY: @{target_a}")
        print("=" * 50)

        meta = profile_a["Case_Evidentiary_Metadata"]
        identity = profile_a["Target_Core_Identity"]
        metrics = profile_a["Platform_Volume_Metrics"]

        print(f"[+] Unique System ID   : {meta['Permanent_Platform_ID_Number']}")
        print(f"[+] Account Age        : {meta['Account_Creation_Date']}")
        print(f"[+] Location Anchor    : {identity['Stated_Geographic_Location']}")
        print(f"[+] Bio Manifest       : {identity['Profile_Bio_Text']}")
        print(f"[+] Following Count    : {metrics['Following_Count_Outbound']}")
        print(f"[+] Followers Count    : {metrics['Followers_Count_Inbound']}")
        print(f"[+] Total Posts Scanned: {metrics['Total_Recent_Posts_Analyzed']}")
        print(f"\n[+] Comprehensive analytical file stored cleanly in: {profile_a_path}")
        print("======================================================")
        return

    # Step 1b: Execute Stage 1 Fuzzy Resolution Discovery for Secondary Target
    print(f"\n[*] Analyzing target string pattern for Phase 2: @{raw_target_b}")
    target_b = discover_suspect_handle_fuzzy(raw_target_b)

    # Step 4: Process Secondary Target Ingestion
    print(f"[*] Launching phase 2 investigation on resolved handle: @{target_b}")
    success_b = fetch_target_profile_rapid(target_b)

    if not success_b:
        print(f"[!] Critical Failure: Unable to parse target profile [@{target_b}]. Pipeline stopped.")
        return

    profile_b_path = os.path.join(CLEAN_REPORT_DIR, f"{target_b}.json")
    with open(profile_b_path, "r", encoding="utf-8") as f:
        profile_b = json.load(f)

    # Step 5: Real platform-verified mutual-follow check
    print("\n[*] Querying platform-verified follow relationship...")
    mutual_follow_result = check_follow_relationship(target_a, target_b)
    if mutual_follow_result is None:
        print("[!] Mutual-follow check skipped (quota exhausted or API error). Scoring will proceed without it.")
    else:
        print(f"[+] Mutual-follow check result: {mutual_follow_result}")

    # Step 6: Run Correlation Matrix Scoring Engine
    print("\n" + "=" * 50)
    print("⚙️ EXECUTING CORRELATION MATRIX ALGORITHMIC SCORING")
    print("=" * 50)

    scorer = ForensicLinkageScorer()
    linkage_report = scorer.compute_linkage_matrix(profile_a, profile_b, mutual_follow=mutual_follow_result)

    comparison_filename = f"{target_a}_{target_b}_linkage_matrix.json"
    comparison_path = os.path.join("evidence_vault", comparison_filename)

    with open(comparison_path, "w", encoding="utf-8") as f:
        json.dump(linkage_report, f, indent=4, ensure_ascii=False)

    print(json.dumps(linkage_report, indent=4))
    print("=" * 50)
    print(f"[+] Admissibility Linkage matrix report written to: {comparison_path}")
    print(f"[*] Quota remaining — twitter_api45: {remaining('twitter_api45')} | twittr_v2: {remaining('twittr_v2')}")


if __name__ == "__main__":
    main()