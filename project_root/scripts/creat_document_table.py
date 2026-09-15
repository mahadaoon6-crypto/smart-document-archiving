import os
import csv

# المسار الرئيسي للآبار
BASE_DIR = r"C:\Users\acc\archive_project\project_root\data\wells"

# ملف الإخراج
OUTPUT_FILE = r"C:\Users\acc\archive_project\project_root\data\metadata\document_table.csv"

# الحقول الأساسية للجدول
FIELDS = [
    "case_file_id",
    "dossier_type",
    "document_state",
    "file_name",
    "file_path"
]

rows = []

# المرور على كل مجلد CaseFile_n
for case_file in os.listdir(BASE_DIR):
    case_path = os.path.join(BASE_DIR, case_file)

    if not os.path.isdir(case_path):
        continue

    # استخراج رقم الإضبارة الجديد
    case_file_id = case_file.replace("CaseFile_", "")

    # المرور على فهارس الإضبارة (licenses / estate / inspection / support)
    for dossier in os.listdir(case_path):
        dossier_path = os.path.join(case_path, dossier)

        if not os.path.isdir(dossier_path):
            continue

        dossier_type = dossier  # نوع الوثيقة

        # المرور مباشرة على الملفات داخل الفهرس
        for file_name in os.listdir(dossier_path):
            file_path = os.path.join(dossier_path, file_name)

            # تجاهل أي شيء غير الصور
            if not file_name.lower().endswith((".jpg", ".jpeg", ".png")):
                continue

            rows.append({
                "case_file_id": case_file_id,
                "dossier_type": dossier_type,
                "document_state": "done",  # كما في المرحلة الأولى
                "file_name": file_name,
                "file_path": file_path.replace("\\", "/")
            })

# كتابة الجدول إلى CSV
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)

print("Document Table created successfully!")
print(f"Total documents indexed: {len(rows)}")
