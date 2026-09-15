import easyocr
import tempfile
import os

# إعداد القارئ مرة واحدة فقط
reader = easyocr.Reader(
    ['ar'],
    model_storage_directory=r"C:\Users\acc\.EasyOCR\models",
    download_enabled=False
)

def extract_text(uploaded_file):
    """
    uploaded_file: ملف مرفوع من Django (InMemoryUploadedFile)
    """
    # حفظ الملف مؤقتًا
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, uploaded_file.name)

    with open(temp_path, "wb") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)

    # تشغيل OCR
    results = reader.readtext(temp_path)

    # دمج النصوص
    text = "\n".join([res[1] for res in results])

    return text
