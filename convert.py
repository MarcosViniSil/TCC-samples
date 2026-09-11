import json

input_file = "gnome.json"
output_file = "gnome.jsonl"

with open(input_file, "r", encoding="utf-8") as json_file:
    data = json.load(json_file)

with open(output_file, "w", encoding="utf-8") as jsonl_file:
    for register in data:
        jsonl_file.write(json.dumps(register, ensure_ascii=False) + "\n")
