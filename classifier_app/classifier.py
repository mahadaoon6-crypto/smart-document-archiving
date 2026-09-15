# ملف التصنيف الرئيسي
import os
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import AutoTokenizer, AutoModel

from classifier_app.text_cleaning import clean_text
from classifier_app.models import TrainingDomain, HumanIndex

# -----------------------------
# المسارات
# -----------------------------
BASE_DIR = r"C:\Users\acc\archive_project\project_root\data"
PROJECTION_MODEL_PATH = os.path.join(BASE_DIR, "self_supervised_projection.pt")
CLASSIFIER_MODEL_PATH = os.path.join(BASE_DIR, "classifier_model.pt")

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# -----------------------------
# 1) تحميل CAMeLBERT
# -----------------------------
MODEL_NAME = "CAMeL-Lab/bert-base-arabic-camelbert-msa"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
bert_model = AutoModel.from_pretrained(MODEL_NAME).to(device)
bert_model.eval()

def get_embedding(text: str):
    cleaned = clean_text(text)
    inputs = tokenizer(
        cleaned,
        return_tensors="pt",
        truncation=True,
        max_length=512
    ).to(device)

    with torch.no_grad():
        outputs = bert_model(**inputs)

    emb = outputs.last_hidden_state[:, 0, :].squeeze().detach().cpu().numpy()
    return emb.astype("float32")  # شكلها (768,)


# -----------------------------
# 2) ProjectionHead كما في التدريب
# -----------------------------
class ProjectionHead(nn.Module):
    def __init__(self, input_dim=768, hidden_dim=256, output_dim=128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, output_dim)
        )

    def forward(self, x):
        return self.net(x)

projection_model = ProjectionHead().to(device)
projection_model.load_state_dict(
    torch.load(PROJECTION_MODEL_PATH, map_location=device)
)
projection_model.eval()

# -----------------------------
# 3) Classifier كما في train_classifier_new.py
# -----------------------------
class Classifier(nn.Module):
    def __init__(self, input_dim=896, num_classes=4):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, num_classes)
        )

    def forward(self, x):
        return self.net(x)

classifier_model = Classifier().to(device)
classifier_model.load_state_dict(
    torch.load(CLASSIFIER_MODEL_PATH, map_location=device)
)
classifier_model.eval()


# -----------------------------
# 4) دالة التصنيف النهائية
# -----------------------------
def classify_document(document):
    """
    دالة التصنيف الأساسية — تعيد الفهرس الصحيح للوثيقة
    """

    # ---------------------------------------------
    # 1) الحصول على المشروع الفعّال
    # ---------------------------------------------
    active_domain = TrainingDomain.objects.filter(is_active=True).first()
    if not active_domain or not active_domain.is_trained:
        return None   # النظام غير مدرّب → لا يمكن التصنيف

    # ---------------------------------------------
    # 2) الحصول على فهارس المشروع الفعّال
    # ---------------------------------------------
    indexes = HumanIndex.objects.filter(domain=active_domain)
    index_names = [idx.name for idx in indexes]

    # ---------------------------------------------
    # 3) قراءة النص
    # ---------------------------------------------
    text = document.ocr_text or ""
    if not text.strip():
        return None

    # ---------------------------------------------
    # 4) استخراج التمثيل الأصلي CAMeLBERT
    # ---------------------------------------------
    emb = get_embedding(text)
    emb_tensor = torch.from_numpy(emb).unsqueeze(0).to(device)

    # ---------------------------------------------
    # 5) استخراج التمثيل الذاتي (Projection Head)
    # ---------------------------------------------
    with torch.no_grad():
        z = projection_model(emb_tensor)           # (1, 128)

    # ---------------------------------------------
    # 6) التمثيل المدمج
    # ---------------------------------------------
    combined = torch.cat([emb_tensor, z], dim=1)   # (1, 896)

    # ---------------------------------------------
    # 7) تشغيل طبقة التصنيف المدربة
    # ---------------------------------------------
    with torch.no_grad():
        logits = classifier_model(combined)
        probs = F.softmax(logits, dim=1).cpu().numpy()[0]

    # ---------------------------------------------
    # 8) اختيار أعلى احتمال
    # ---------------------------------------------
    best_index = np.argmax(probs)
    predicted_label = index_names[best_index]

    # ---------------------------------------------
    # 9) إعادة كائن الفهرس نفسه
    # ---------------------------------------------
    return indexes.get(name=predicted_label)

