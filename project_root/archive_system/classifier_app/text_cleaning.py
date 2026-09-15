import re

def clean_text(text):
    if not text:
        return ""

    text = re.sub(r"[^\u0600-\u06FF0-9\s\.:\/\-]", " ", text)
    text = re.sub(r"\s+", " ", text)

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    text = "\n".join(lines)

    replacements = {
        "المايية": "المائية",
        "الهيية": "الهيئة",
        "اليازدية": "الياذدية",
        "البير": "البئر",
    }

    for wrong, correct in replacements.items():
        text = text.replace(wrong, correct)

    return text.strip()
