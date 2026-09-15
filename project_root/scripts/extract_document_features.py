import os
import csv
import easyocr

# =========================================================
# إعداد EasyOCR
# =========================================================

reader = easyocr.Reader(
    ['ar'],
    model_storage_directory=r"C:\Users\acc\.EasyOCR\models",
    download_enabled=False
)

# =========================================================
# مسارات الإدخال والإخراج
# =========================================================

WELLS_DIR = r"C:\Users\acc\archive_project\project_root\data\wells"
OUTPUT_DIR = r"C:\Users\acc\archive_project\project_root\data\ocr_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# اختصارات الفهارس
FOLDER_SHORT = {
    "licenses": "lic",
    "inspection": "ins",
    "estate": "est",
    "support": "sup"
}

# =========================================================
# معالجة صورة واحدة
# =========================================================

def process_image(image_path, output_csv):
    results = reader.readtext(image_path)

    lines = []
    for box, text, conf in results:
        lines.append((text, conf))

    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["line_number", "raw_text", "confidence"])
        for i, (raw_text, conf) in enumerate(lines, start=1):
            writer.writerow([i, raw_text, round(conf, 4)])

    print(f"✔ تم حفظ: {output_csv}")

# =========================================================
# المرور على جميع الوثائق داخل wells
# =========================================================

def main():

    processed = 0

    for casefile in os.listdir(WELLS_DIR):
        casefile_path = os.path.join(WELLS_DIR, casefile)

        if not os.path.isdir(casefile_path):
            continue

        # المرور على الفهارس داخل كل CaseFile
        for folder in os.listdir(casefile_path):
            folder_path = os.path.join(casefile_path, folder)

            if not os.path.isdir(folder_path):
                continue

            # اختصار الفهرس
            folder_key = FOLDER_SHORT.get(folder, folder[:3])

            # المرور على الوثائق داخل الفهرس
            for filename in os.listdir(folder_path):

                if not filename.lower().endswith((".jpg", ".jpeg", ".png")):
                    continue

                image_path = os.path.join(folder_path, filename)

                # اسم ملف CSV الجديد
                base_name = os.path.splitext(filename)[0]
                new_csv_name = f"{casefile}_{folder_key}_{base_name}.csv"

                output_csv = os.path.join(OUTPUT_DIR, new_csv_name)

                print(f"\n📄 معالجة: {image_path}")
                process_image(image_path, output_csv)

                processed += 1

    print("\n==============================================")
    print(f"✔ عدد الوثائق التي تمت معالجتها: {processed}")
    print(f"📁 الملفات موجودة في: {OUTPUT_DIR}")
    print("==============================================")

# =========================================================

if __name__ == "__main__":
    main()