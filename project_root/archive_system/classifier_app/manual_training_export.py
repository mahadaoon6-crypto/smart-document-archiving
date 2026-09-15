import json
import pandas as pd
import torch
import os
from classifier_app.models import ManualIndex, TrainingDomain
from classifier_app.classifier import get_embedding, projection_model, device
from django.conf import settings

def export_manual_training_dataset():

    rows = []

    export_path = os.path.join(settings.MEDIA_ROOT, "training_exports", "manual_training_dataset.csv")

    # حذف الملف القديم
    if os.path.exists(export_path):
        os.remove(export_path)

    # ⭐ الحصول على المشروع الفعّال
    active_domain = TrainingDomain.objects.filter(is_active=True).first()
    if not active_domain:
        return

    # ⭐ أخذ التصحيحات الخاصة بالمشروع الفعّال فقط
    manual_items = ManualIndex.objects.filter(document__domain=active_domain)

    for item in manual_items:

        doc = item.document

        # النص المستخرج من OCR
        text = doc.ocr_text if doc.ocr_text else ""

        # استخراج embedding الأصلي
        emb = get_embedding(text)
        emb_list = emb.astype(float).tolist()

        # استخراج التمثيل الذاتي
        emb_tensor = torch.from_numpy(emb).unsqueeze(0).to(device)
        with torch.no_grad():
            z = projection_model(emb_tensor).cpu().numpy()[0]

        z_list = z.astype(float).tolist()

        # دمج التمثيلين
        combined_list = emb_list + z_list

        rows.append({
            "text": text,
            "corrected_label": item.corrected_label,
            "emb": json.dumps(emb_list),
            "z": json.dumps(z_list),
            "combined": json.dumps(combined_list)
        })

    df = pd.DataFrame(rows)
    df.to_csv(export_path, index=False)

