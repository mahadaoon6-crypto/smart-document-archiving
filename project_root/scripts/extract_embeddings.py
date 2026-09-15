import os
import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModel

# ---------------------------------------------------------
# 1) استيراد دالة تنظيف النصوص
# ---------------------------------------------------------
from text_cleaning import clean_text

# ---------------------------------------------------------
# 2) تحميل نموذج CAMeLBERT
# ---------------------------------------------------------
MODEL_NAME = "CAMeL-Lab/bert-base-arabic-camelbert-msa"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModel.from_pretrained(MODEL_NAME)

# ---------------------------------------------------------
# 3) دالة استخراج embedding
# ---------------------------------------------------------
def get_embedding(text):
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=512
    )

    with torch.no_grad():
        outputs = model(**inputs)

    embedding = outputs.last_hidden_state[:, 0, :].squeeze().numpy()
    return embedding

# ---------------------------------------------------------
# 4) المسارات
# ---------------------------------------------------------
OCR_DIR = r"C:\Users\acc\archive_project\project_root\data\ocr_output"
DATASET_PATH = r"C:\Users\acc\archive_project\project_root\data\dataset.csv"
EMB_OUTPUT_PATH = r"C:\Users\acc\archive_project\project_root\data\embeddings.npy"

# ---------------------------------------------------------
# إنشاء ملفات fulltext.txt لكل وثيقة OCR
# ---------------------------------------------------------
for filename in os.listdir(OCR_DIR):
    if filename.lower().endswith(".csv"):
        csv_path = os.path.join(OCR_DIR, filename)
        fulltext_path = csv_path.replace(".csv", "_fulltext.txt")

        # قراءة النص من ملف CSV
        df_csv = pd.read_csv(csv_path)
        lines = df_csv["raw_text"].astype(str).tolist()

        # كتابة النص الكامل في ملف fulltext.txt
        with open(fulltext_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"✔ تم إنشاء النص الكامل: {fulltext_path}")


# ---------------------------------------------------------
# 5) بناء dataset.csv من كل ملفات OCR
# ---------------------------------------------------------
rows = []

for filename in os.listdir(OCR_DIR):
    if filename.lower().endswith(".csv"):
        full_path = os.path.join(OCR_DIR, filename)

        # استخراج نوع الوثيقة من اسم الملف
        parts = filename.split("_")
        casefile = parts[1]            # CaseFile_001
        folder_short = parts[2]        # lic / ins / est / sup
        doc_name = "_".join(parts[2:]) # Doc 13.csv

        rows.append({
            "document_name": filename,
            "document_type": folder_short,
            "source": casefile,
            "keywords_found": "",
            "region_present": False,
            "subdistrict_present": False,
            "estate_present": False,
            "well_present": False,
            "full_text_path": full_path.replace(".csv", "_fulltext.txt")
        })

df = pd.DataFrame(rows)
df.to_csv(DATASET_PATH, index=False, encoding="utf-8-sig")

print("✔ تم إنشاء dataset.csv الجديد ويحتوي على كل وثائق OCR")

# ---------------------------------------------------------
# 6) استخراج embeddings لكل وثيقة
# ---------------------------------------------------------
embeddings = []

for idx, row in df.iterrows():
    text_path = row["full_text_path"]

    if not os.path.exists(text_path):
        print(f"⚠ الملف غير موجود: {text_path}")
        embeddings.append(np.zeros(768))
        continue

    with open(text_path, "r", encoding="utf-8") as f:
        raw_text = f.read()

    cleaned = clean_text(raw_text)
    emb = get_embedding(cleaned)

    embeddings.append(emb)

    print(f"✔ معالجة الوثيقة رقم {idx+1}: {row['document_name']}")

# ---------------------------------------------------------
# 7) حفظ embeddings في ملف NumPy
# ---------------------------------------------------------
emb_array = np.array(embeddings)
np.save(EMB_OUTPUT_PATH, emb_array)

print("\n==============================================")
print(f"✔ تم حفظ ملف التمثيلات النصية في: {EMB_OUTPUT_PATH}")
print("==============================================\n")

# ---------------------------------------------------------
# 8) دمج embeddings داخل dataset.csv
# ---------------------------------------------------------
# دمج الأعمدة دفعة واحدة لتجنب التحذير
emb_df = pd.DataFrame(emb_array, columns=[f"emb_{i}" for i in range(768)])

df = pd.concat([df, emb_df], axis=1)

df.to_csv(DATASET_PATH, index=False, encoding="utf-8-sig")

print("✔ تم دمج التمثيلات النصية داخل dataset.csv")
print("✔ المشروع جاهز لمرحلة التعلم الذاتي والتصنيف")
