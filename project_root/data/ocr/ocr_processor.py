
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    Image.open("C:\Users\acc\Desktop\المشروع\project_root\data\wells\CaseFile_001\settlement\clean\1.JPG"),
    lang="ara"
)

print("text")
