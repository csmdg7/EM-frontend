import os
import json
import sys


def generate_graph_datasets(username: str):
    clean_username = username.strip().lstrip("@")
    report_path = os.path.join("evidence_vault", ".clean_report", f"{clean_username}.json")

    if not os.path.exists(report_path):
        print(f"[!] Error: No data matrix profile found for @{clean_username}")
        return None

    with open(report_path, "r", encoding="utf-8") as f:
        profile_data = json.load(f)

    analysis_data = profile_data.get("Behavioral_Frequency_Analysis", {})
    hourly_source = analysis_data.get("Temporal_Hourly_Post_Profile_UTC", {})
    network_source = analysis_data.get("Most_Interacted_With_Handles", {})

    bar_labels = sorted(list(hourly_source.keys()))
    bar_values = [hourly_source[hour] for hour in bar_labels]

    donut_labels = list(network_source.keys())
    donut_values = list(network_source.values())

    if not donut_labels:
        donut_labels = ["No Interacted Handles Found"]
        donut_values = [1]

    graph_payload = {
        "Target_Scope": clean_username,
        "Using_Simulation_Data": False,
        "Temporal_Bar_Chart": {
            "Labels_X_Axis": bar_labels,
            "Datasets_Y_Axis": bar_values
        },
        "Interaction_Network_Pie_Chart": {
            "Labels_Categories": donut_labels,
            "Datasets_Distribution": donut_values
        }
    }

    graph_output_dir = os.path.join("evidence_vault", "front_end_assets")
    os.makedirs(graph_output_dir, exist_ok=True)

    output_path = os.path.join(graph_output_dir, f"{clean_username}_graphs.json")
    with open(output_path, "w", encoding="utf-8") as out_f:
        json.dump(graph_payload, out_f, indent=4)

    print(f"\n[+][GRAPH CONFIG] Front-end chart vectors mapped successfully!")
    print(f"[*] Visual asset JSON available at: {output_path}")
    return graph_payload


def generate_linkage_knowledge_graph(target_a: str, target_b: str):
    """
    Builds a node-link JSON (nodes/links schema) from a pairwise linkage report,
    suitable for direct consumption by vis.js, Cytoscape.js, or d3 on the frontend.
    Run this AFTER main.py has produced the {a}_{b}_linkage_matrix.json file.
    """
    a_clean = target_a.strip().lstrip("@")
    b_clean = target_b.strip().lstrip("@")

    linkage_path = os.path.join("evidence_vault", f"{a_clean}_{b_clean}_linkage_matrix.json")
    if not os.path.exists(linkage_path):
        # main.py may have written it in the other name order
        linkage_path = os.path.join("evidence_vault", f"{b_clean}_{a_clean}_linkage_matrix.json")
        if not os.path.exists(linkage_path):
            print(f"[!] Error: No linkage matrix found for @{a_clean} / @{b_clean}. Run main.py first.")
            return None

    with open(linkage_path, "r", encoding="utf-8") as f:
        linkage_report = json.load(f)

    knowledge_graph = {
        "nodes": [
            {"id": a_clean, "type": "account", "label": f"@{a_clean}"},
            {"id": b_clean, "type": "account", "label": f"@{b_clean}"}
        ],
        "links": [
            {
                "source": a_clean,
                "target": b_clean,
                "weight": linkage_report["Overall_Linkage_Score"],
                "classification": linkage_report["Confidence_Classification"],
                "signals_corroborated": linkage_report.get("Signals_Corroborated", 0),
                "breakdown": linkage_report["Vector_Analysis_Breakdown"]
            }
        ]
    }

    graph_output_dir = os.path.join("evidence_vault", "front_end_assets")
    os.makedirs(graph_output_dir, exist_ok=True)

    output_path = os.path.join(graph_output_dir, f"{a_clean}_{b_clean}_knowledge_graph.json")
    with open(output_path, "w", encoding="utf-8") as out_f:
        json.dump(knowledge_graph, out_f, indent=4)

    print(f"[+][KNOWLEDGE GRAPH] Node-link graph exported to: {output_path}")
    return knowledge_graph


if __name__ == "__main__":
    if len(sys.argv) == 2:
        generate_graph_datasets(sys.argv[1])
    elif len(sys.argv) == 3:
        generate_graph_datasets(sys.argv[1])
        generate_graph_datasets(sys.argv[2])
        generate_linkage_knowledge_graph(sys.argv[1], sys.argv[2])
    else:
        user_target = input("Enter target handle to build graph vectors for: ")
        if user_target.strip():
            generate_graph_datasets(user_target)