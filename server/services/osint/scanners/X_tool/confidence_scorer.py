import math
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

try:
    import Levenshtein
    _HAS_LEVENSHTEIN = True
except ImportError:
    _HAS_LEVENSHTEIN = False

class ForensicLinkageScorer:
    """
    Evaluates correlation heuristics across profile identity, behavior matrices,
    network structures, and direct platform-verified relationships to compute
    an admissibility confidence rating.
    """

    @staticmethod
    def evaluate_spatial_alignment(loc_a: str, loc_b: str) -> float:
        """Weight: 20 Points."""
        if not loc_a or not loc_b or loc_a.upper() == "NOT SPECIFIED" or loc_b.upper() == "NOT SPECIFIED":
            return 0.0
        a_clean = loc_a.strip().lower()
        b_clean = loc_b.strip().lower()
        if a_clean == b_clean and a_clean != "":
            return 20.0
        if a_clean in b_clean or b_clean in a_clean:
            return 12.0
        return 0.0

    @staticmethod
    def evaluate_linguistic_similarity(bio_a: str, bio_b: str) -> float:
        """Weight: 15 Points."""
        if not bio_a or not bio_b or not bio_a.strip() or not bio_b.strip():
            return 0.0
        try:
            vectorizer = TfidfVectorizer(stop_words="english")
            tfidf_matrix = vectorizer.fit_transform([bio_a, bio_b])
            similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
            return round(similarity * 15.0, 2)
        except ValueError:
            return 0.0

    @staticmethod
    def evaluate_username_similarity(user_a: str, user_b: str) -> float:
        """Weight: 15 Points."""
        if not user_a or not user_b:
            return 0.0
        a_clean = user_a.strip().lower()
        b_clean = user_b.strip().lower()
        if a_clean == b_clean:
            return 0.0
        if _HAS_LEVENSHTEIN:
            distance = Levenshtein.distance(a_clean, b_clean)
        else:
            distance = ForensicLinkageScorer._fallback_levenshtein(a_clean, b_clean)
        max_len = max(len(a_clean), len(b_clean), 1)
        similarity_ratio = 1 - (distance / max_len)
        if similarity_ratio > 0.85:
            return 15.0
        elif similarity_ratio > 0.6:
            return 9.0
        elif similarity_ratio > 0.4:
            return 4.0
        return 0.0

    @staticmethod
    def _fallback_levenshtein(a: str, b: str) -> int:
        if len(a) < len(b):
            a, b = b, a
        previous_row = range(len(b) + 1)
        for i, ca in enumerate(a):
            current_row = [i + 1]
            for j, cb in enumerate(b):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (ca != cb)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        return previous_row[-1]

    @staticmethod
    def evaluate_matrix_overlaps(dict_a: dict, dict_b: dict, max_points: float) -> float:
        """Sub-Weight: 10 Pts each. Handles behavioral timeline data tracking arrays."""
        if not dict_a or not dict_b:
            return 0.0
        keys_a = set(dict_a.keys())
        keys_b = set(dict_b.keys())
        keys_a.discard("#general_updates")
        keys_b.discard("#general_updates")
        shared_elements = keys_a.intersection(keys_b)
        if not shared_elements:
            return 0.0
        score = max_points * 0.5
        total_elements = len(keys_a.union(keys_b))
        overlap_ratio = len(shared_elements) / total_elements if total_elements > 0 else 0
        score += (overlap_ratio * (max_points * 0.5))
        return round(score, 2)

    @staticmethod
    def evaluate_account_age_proximity(created_a: str, created_b: str) -> float:
        """Weight: 10 Points."""
        if not created_a or not created_b or created_a == "NOT PROVIDED BY API" or created_b == "NOT PROVIDED BY API":
            return 0.0
        twitter_fmt = "%a %b %d %H:%M:%S %z %Y"
        try:
            date_a = datetime.strptime(created_a, twitter_fmt)
            date_b = datetime.strptime(created_b, twitter_fmt)
        except (ValueError, TypeError):
            return 0.0
        gap_days = abs((date_a - date_b).days)
        if gap_days < 7:
            return 10.0
        elif gap_days < 30:
            return 6.0
        elif gap_days < 90:
            return 2.0
        return 0.0

    @staticmethod
    def evaluate_mutual_follow(is_follow_result) -> float:
        """Weight: 20 Points."""
        if is_follow_result is True:
            return 20.0
        return 0.0

    def compute_linkage_matrix(self, profile_a: dict, profile_b: dict, mutual_follow=None) -> dict:
        """
        Aggregates all algorithmic vectors into a single confidence rating.
        Features timeline data starvation protection mechanics.
        """
        identity_a = profile_a.get("Target_Core_Identity", {})
        identity_b = profile_b.get("Target_Core_Identity", {})
        meta_a = profile_a.get("Case_Evidentiary_Metadata", {})
        meta_b = profile_b.get("Case_Evidentiary_Metadata", {})
        matrices_a = profile_a.get("Behavioral_Frequency_Analysis", {})
        matrices_b = profile_b.get("Behavioral_Frequency_Analysis", {})

        # Track total dynamically configurable matrix limits
        available_max_weight = 100.0
        
        # Pull profile timeline size metrics
        posts_v1 = profile_a.get("Platform_Volume_Metrics", {}).get("Total_Recent_Posts_Analyzed", 0)
        posts_v2 = profile_b.get("Platform_Volume_Metrics", {}).get("Total_Recent_Posts_Analyzed", 0)

        # Baseline Calculations
        geo_score = self.evaluate_spatial_alignment(identity_a.get("Stated_Geographic_Location", ""), identity_b.get("Stated_Geographic_Location", ""))
        bio_score = self.evaluate_linguistic_similarity(identity_a.get("Profile_Bio_Text", ""), identity_b.get("Profile_Bio_Text", ""))
        username_score = self.evaluate_username_similarity(identity_a.get("Target_Username", ""), identity_b.get("Target_Username", ""))
        age_score = self.evaluate_account_age_proximity(meta_a.get("Account_Creation_Date", ""), meta_b.get("Account_Creation_Date", ""))
        mutual_score = self.evaluate_mutual_follow(mutual_follow)

        # Behavioral Timeline Vector Starvation Defensive Safety Overrides
        if (isinstance(posts_v1, int) and posts_v1 < 3) or (isinstance(posts_v2, int) and posts_v2 < 3) or \
           (isinstance(matrices_a.get("Captured_Public_Timeline_Data"), str)):
            # Timeline data is starved (e.g., @claude case study) -> Nullify behavioral weights safely
            hashtag_score = 0.0
            mention_score = 0.0
            available_max_weight -= 20.0  # Subtract 10pts for hashtags, 10pts for mentions
        else:
            hashtag_score = self.evaluate_matrix_overlaps(matrices_a.get("Most_Used_Hashtags_Clustering", {}), matrices_b.get("Most_Used_Hashtags_Clustering", {}), max_points=10.0)
            mention_score = self.evaluate_matrix_overlaps(matrices_a.get("Most_Interacted_With_Handles", {}), matrices_b.get("Most_Interacted_With_Handles", {}), max_points=10.0)

        all_vectors = {
            "Geographic_Coincidence_Points": geo_score,
            "Bio_TFIDF_Similarity": bio_score,
            "Username_Fuzzy_Match": username_score,
            "Hashtag_Clustering_Alignment": hashtag_score,
            "Interaction_Network_Alignment": mention_score,
            "Account_Age_Proximity": age_score,
            "Mutual_Follow_Verified": mutual_score,
        }

        active_signals = sum(1 for v in all_vectors.values() if v > 0)
        raw_sum = sum(all_vectors.values())
        
        # Dynamically scale back up to base 100 threshold matrix
        total_linkage = round((raw_sum / available_max_weight) * 100.0, 2)

        # Minimum-3-Signal Gate System Circuit Breaker
        if total_linkage >= 70.0 and active_signals < 3:
            confidence = "MEDIUM — INSUFFICIENT SIGNAL CORROBORATION (capped from HIGH)"
            total_linkage = min(total_linkage, 69.0)
        elif total_linkage >= 70.0:
            confidence = "HIGH — COURT-ADMISSIBLE INFERENCE INDICATOR"
        elif total_linkage >= 45.0:
            confidence = "MEDIUM — STRUCTURAL NODAL COUPLING"
        else:
            confidence = "LOW — INDEPENDENT PLATFORM PRESENCE"

        return {
            "Overall_Linkage_Score": total_linkage,
            "Confidence_Classification": confidence,
            "Signals_Corroborated": active_signals,
            "Mutual_Follow_Check_Status": (
                "NOT PERFORMED (quota/error)" if mutual_follow is None
                else ("CONFIRMED" if mutual_follow else "NO RELATIONSHIP FOUND")
            ),
            "Vector_Analysis_Breakdown": {
                "Geographic_Coincidence_Points": geo_score,
                "Mutual_Follow_Verified": mutual_score,
                "Behavioral_Fingerprint_Metrics": {
                    "Bio_TFIDF_Similarity": bio_score,
                    "Username_Fuzzy_Match": username_score,
                    "Hashtag_Clustering_Alignment": hashtag_score,
                    "Interaction_Network_Alignment": mention_score,
                    "Account_Age_Proximity": age_score,
                }
            }
        }