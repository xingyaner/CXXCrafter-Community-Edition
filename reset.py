import yaml

with open("projects.yaml", "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)

for entry in data:
    entry['fixed_state'] = 'no'
    entry.pop('fix_result', None)
    entry.pop('fix_date', None)

with open("projects.yaml", "w", encoding="utf-8") as f:
    yaml.dump(data, f, default_flow_style=False, sort_keys=False)
print("✅ All projects in projects.yaml have been reset to 'no'.")
