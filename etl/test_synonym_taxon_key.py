import requests
import pprint

# --- Step 1: resolve a known synonym pair ---
match = requests.get(
    "https://api.gbif.org/v2/species/match",
    params={"scientificName": "Oreomecon alborosea"}
).json()

print("=== RAW MATCH RESPONSE ===")
pprint.pprint(match)  # inspect this directly — don't trust field names below blindly

synonym_key = match.get("usage", {}).get("key")
synonym_status = match.get("usage", {}).get("status")

# "acceptedUsage" is the nested field for the accepted taxon when synonym=True —
accepted_key = match.get("acceptedUsage", {}).get("key") if match.get("synonym") else None

print(f"\nInput name resolved as: status={synonym_status}, synonym_flag={match.get('synonym')}")
print(f"Synonym's own key: {synonym_key}")
print(f"Accepted key (if found): {accepted_key}")

if match.get("synonym") and accepted_key is None:
    print("\n*** acceptedUsage.key not found at that path — check the raw dict above "
          "for the correct field name before trusting the comparison below. ***")

# --- Step 2: compare occurrence counts using each key ---
def occurrence_count(key, label):
    if key is None:
        print(f"{label}: skipped, no key available")
        return None
    resp = requests.get(
        "https://api.gbif.org/v1/occurrence/search",
        params={"taxonKey": key, "country": "CA", "limit": 1}  # limit=1, we only need `count`
    ).json()
    print(f"{label} (taxonKey={key}): count = {resp['count']}")
    return resp["count"]

print("\n=== OCCURRENCE COUNT COMPARISON ===")
synonym_count = occurrence_count(synonym_key, "Synonym key")
accepted_count = occurrence_count(accepted_key, "Accepted key")

if synonym_count is not None and accepted_count is not None:
    if accepted_count > synonym_count:
        print(f"\nConfirmed asymmetric: accepted key returns {accepted_count} vs "
              f"synonym key's {synonym_count}. Using usage.key alone would have undercounted.")
    elif accepted_count == synonym_count:
        print("\nCounts are equal — either the asymmetry doesn't apply here, "
              "or GBIF already merges these in its interpreted index. Don't generalize "
              "from one species; the earlier claim was about mechanism, not magnitude.")
    else:
        print("\nUnexpected: synonym key returned MORE than accepted key. "
              "Worth re-reading the raw response before trusting either number.")