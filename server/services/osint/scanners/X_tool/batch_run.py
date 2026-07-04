import os
import sys
import json
import itertools

from .live_fetch import fetch_target_profile_rapid, discover_suspect_handle_fuzzy
from .confidence_scorer import ForensicLinkageScorer
from .manual_check import check_follow_relationship
from .quota_tracker import remaining

VAULT_DIR = "evidence_vault"
CLEAN_REPORT_DIR = os.path.join(VAULT_DIR, ".clean_report")

os.makedirs(CLEAN_REPORT_DIR, exist_ok=True)


def run_batch_investigation(target_handles: list):
    """
    Automates multi-account profile ingestion and computes an
    all-pairs cross-linkage matrix across the target cluster.
    """
    print("======================================================")
    print("     OSINT BATCH PROCESSING & COORDINATION ENGINE     ")
    print("======================================================\n")

    clean_targets = list(set([h.strip().lstrip("@") for h in target_handles if h.strip()]))

    if len(clean_targets) < 2:
        print("[!] Aborted: Batch operations require a minimum of 2 valid target profiles.")
        return

    print(f"[*] Initializing batch cluster scan for targets: {', '.join(['@' + t for t in clean_targets])}")
    print(f"[*] Quota remaining before run — twitter_api45: {remaining('twitter_api45')} | twittr_v2: {remaining('twittr_v2')}\n")

    # Warn early if quota can't cover the batch (1 profile + 1 timeline call per target, minimum)
    estimated_calls = len(clean_targets) * 2
    if estimated_calls > remaining("twitter_api45"):
        print(f"[!] WARNING: This batch needs ~{estimated_calls} twitter_api45 calls but only "
              f"{remaining('twitter_api45')} remain. Some targets may fall back to cache or fail.\n")

    # Step 1: Sequential Ingestion Pool with Stage 1 Fuzzy Discovery Filtering
    profile_pool = {}
    
    for handle in clean_targets:
        print(f"\n--- Processing Target Stream Evaluation: @{handle} ---")

        # Intercept and convert potential typo variations to real system handles
        resolved_target = discover_suspect_handle_fuzzy(handle)
        
        success = fetch_target_profile_rapid(resolved_target)

        if success:
            report_path = os.path.join(CLEAN_REPORT_DIR, f"{resolved_target}.json")
            try:
                with open(report_path, "r", encoding="utf-8") as f:
                    profile_pool[resolved_target] = json.load(f)
                print(f"[+] Loaded structured payload for @{resolved_target} from clean repository.")
            except Exception as e:
                print(f"[!] Error: Failed to read compiled file for @{resolved_target}: {e}")
        else:
            print(f"[!] Warning: Skipping @{resolved_target} due to profile collection failure.")

    if len(profile_pool) < 2:
        print("\n[!] Critical Failure: Insufficient account data captured to build correlation matrix.")
        return

    print("\n" + "=" * 50)
    print("⚙️ GENERATING CROSS-LINKAGE ASSESSMENT MATRIX")
    print("=" * 50)

    scorer = ForensicLinkageScorer()
    batch_correlations = []

    # Step 2: Pairwise Permutations (Runs automatically on correctly discovered keys)
    for target_a, target_b in itertools.combinations(profile_pool.keys(), 2):
        print(f"[*] Correlating: @{target_a} 🔄 @{target_b}")

        mutual_follow_result = check_follow_relationship(target_a, target_b)
        if mutual_follow_result is None:
            print(f"    [!] Mutual-follow check unavailable for this pair (quota/error) — scoring without it.")

        linkage_report = scorer.compute_linkage_matrix(
            profile_pool[target_a], profile_pool[target_b], mutual_follow=mutual_follow_result
        )

        batch_correlations.append({
            "Pair": [target_a, target_b],
            "Linkage_Percentage_Score": linkage_report["Overall_Linkage_Score"],
            "Forensic_Classification": linkage_report["Confidence_Classification"],
            "Signals_Corroborated": linkage_report["Signals_Corroborated"],
            "Algorithmic_Breakdown": linkage_report["Vector_Analysis_Breakdown"]
        })

    # Step 3: Compile Consolidated Master Dossier
    master_batch_report = {
        "Batch_Metadata": {
            "Total_Monitored_Nodes": len(profile_pool),
            "Total_Computed_Edges": len(batch_correlations),
            "Cluster_Scope": list(profile_pool.keys()),
            "Quota_Remaining_After_Run": {
                "twitter_api45": remaining("twitter_api45"),
                "twittr_v2": remaining("twittr_v2")
            }
        },
        "Computed_Linkage_Matrix": sorted(batch_correlations, key=lambda x: x["Linkage_Percentage_Score"], reverse=True)
    }

    cluster_id = "_".join(sorted(list(profile_pool.keys())[:3]))
    report_filename = f"batch_cluster_{cluster_id}.json"
    report_path = os.path.join(VAULT_DIR, report_filename)

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(master_batch_report, f, indent=4, ensure_ascii=False)

    print("\n" + "📊" + " " + "BATCH MATRIX COMPUTATION PAYLOAD")
    print(json.dumps(master_batch_report, indent=4))
    print("=" * 60)
    print(f"[+] Master cluster briefing file successfully exported to: {report_path}")
    print(f"[*] Quota remaining after run — twitter_api45: {remaining('twitter_api45')} | twittr_v2: {remaining('twittr_v2')}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        targets = sys.argv[1:]
    else:
        raw_input = input("Enter target handles separated by spaces (e.g., google spacex): ")
        targets = raw_input.split()

    run_batch_investigation(targets)