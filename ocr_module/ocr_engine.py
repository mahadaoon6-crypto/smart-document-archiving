import pytesseract
from PIL import Image

# تحديد مسار Tesseract
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def run_ocr_on_image(image_path):
    """
    تشغيل OCR على صورة وإرجاع النص المستخرج
    """
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang="ara")  # اللغة العربية
        return text.strip()
    except Exception as e:
        return f"OCR ERROR: {str(e)}"
