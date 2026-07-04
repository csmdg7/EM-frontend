def format_intel_summary(profile: dict) -> str:
    """Formats updated target records into structured forensic intelligence cards."""
    identity = profile.get("Target_Core_Identity", {})
    metrics = profile.get("Platform_Volume_Metrics", {})
    timeline = profile.get("Captured_Public_Timeline_Data", [])
    audit = profile.get("Audit_Trail", {})

    summary = f"""
======================================================
OSINT INTEL RECORD DOSSIER: @{identity.get('Target_Username', 'UNKNOWN').upper()}
======================================================
Display Name : {identity.get('Target_Display_Name', 'N/A')}
Location Ref : {identity.get('Stated_Geographic_Location', 'NOT SPECIFIED')}
Avatar URL   : {identity.get('Avatar_Image_URL', 'NOT CAPTURED')}
Followers    : {metrics.get('Followers_Count_Inbound', 0)}
Following    : {metrics.get('Following_Count_Outbound', 0)}
Total Posts  : {metrics.get('Lifetime_Total_Posts_Posted', 0)}
Profile Bio  : {identity.get('Profile_Bio_Text', '').strip()}

Data Source  : {audit.get('Data_Source', 'NOT RECORDED')}
Collected At : {audit.get('Collection_Timestamp_UTC', 'NOT RECORDED')}

Recent Broadcast Public Log Entries (Latest 4 Nodes):
------------------------------------------------------"""

    if isinstance(timeline, list):
        for idx, tweet in enumerate(timeline[:4], 1):
            msg = tweet.get("Message_Content", "")
            timestamp = tweet.get("Broadcast_Timestamp", "N/A")

            # Ensure non-ascii text converts cleanly to stdout string formatting
            msg_clean = msg.encode('utf-8', errors='ignore').decode('utf-8')
            truncated_msg = msg_clean if len(msg_clean) < 75 else msg_clean[:72] + "..."
            summary += f"\n  [{idx}] ({timestamp}) -> {truncated_msg}"
    else:
        summary += f"\n  [!] {timeline}"

    summary += "\n======================================================\n"
    return summary


def format_linkage_summary(linkage_report: dict, target_a: str, target_b: str) -> str:
    """Formats a pairwise linkage report into a readable investigator summary."""
    breakdown = linkage_report.get("Vector_Analysis_Breakdown", {})
    behavioral = breakdown.get("Behavioral_Fingerprint_Metrics", {})

    summary = f"""
======================================================
LINKAGE ASSESSMENT: @{target_a.upper()} <-> @{target_b.upper()}
======================================================
Overall Score        : {linkage_report.get('Overall_Linkage_Score', 0)} / 100
Classification        : {linkage_report.get('Confidence_Classification', 'UNKNOWN')}
Signals Corroborated   : {linkage_report.get('Signals_Corroborated', 0)}
Mutual Follow Status   : {linkage_report.get('Mutual_Follow_Check_Status', 'NOT PERFORMED')}

--- Vector Breakdown ---
Geographic Points      : {breakdown.get('Geographic_Coincidence_Points', 0)}
Mutual Follow Points    : {breakdown.get('Mutual_Follow_Verified', 0)}
Bio TF-IDF Similarity   : {behavioral.get('Bio_TFIDF_Similarity', 0)}
Username Fuzzy Match    : {behavioral.get('Username_Fuzzy_Match', 0)}
Hashtag Overlap         : {behavioral.get('Hashtag_Clustering_Alignment', 0)}
Mention Overlap         : {behavioral.get('Interaction_Network_Alignment', 0)}
Account Age Proximity   : {behavioral.get('Account_Age_Proximity', 0)}
======================================================
"""
    return summary