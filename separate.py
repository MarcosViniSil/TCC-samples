import json

input_file_en = "OpenSubtitles.en-pt_BR.en"
input_file_pt = "OpenSubtitles.en-pt_BR.pt_BR"

output_name = input_file_en.split(".")[0]
output = f"{output_name}.jsonl"

with open(input_file_en, encoding="utf-8") as en_file, open(
    input_file_pt, encoding="utf-8"
) as pt_file, open(output, "w", encoding="utf-8") as out_file:

    for idx, (en, pt) in enumerate(zip(en_file, pt_file), start=1):

        en_clean = en.rstrip("\n")
        pt_clean = pt.rstrip("\n")

        if not en_clean or not pt_clean:
            continue

        register = {"id": idx, "en": en_clean, "pt": pt_clean}

        out_file.write(json.dumps(register, ensure_ascii=False) + "\n")
