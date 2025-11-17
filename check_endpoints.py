import re

with open('backend.py', 'r', encoding='utf-8') as f:
    content = f.read()

routes = re.findall(r"@app\.route\([^)]+\)", content)
endpoints = re.findall(r"endpoint='([^']+)'", content)

print(f"Total routes: {len(routes)}")
print(f"Total endpoints: {len(endpoints)}")
print(f"Unique endpoints: {len(set(endpoints))}")

if len(endpoints) != len(set(endpoints)):
    print("❌ DUPLICATE ENDPOINTS FOUND:")
    from collections import Counter
    dupes = [e for e, count in Counter(endpoints).items() if count > 1]
    print(dupes)
else:
    print("✅ All endpoints are unique")

if len(routes) != len(endpoints):
    print(f"⚠️  WARNING: {len(routes) - len(endpoints)} routes missing explicit endpoints")
