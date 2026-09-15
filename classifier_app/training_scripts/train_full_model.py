import torch
import torch.nn as nn
import pandas as pd
import ast
from classifier_app.models import TrainingStatus
from classifier_app.model import FullModel

def train_full_model():

    # تحميل ملف التدريب الجديد
    import os
    from django.conf import settings

    training_file = os.path.join(
        settings.MEDIA_ROOT,
        "training_exports",
        "manual_training_dataset.csv"
    )

    df = pd.read_csv(training_file)



    # تحويل التمثيل المدمج إلى Tensor
    X = torch.tensor(df["combined"].apply(ast.literal_eval).tolist(), dtype=torch.float32)

    # الفئة الرقمية الصحيحة
    y = torch.tensor(df["corrected_label_id"].tolist(), dtype=torch.long)

    # إنشاء النموذج الكامل
    model = FullModel()

    # إعدادات التدريب
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-4)
    loss_fn = nn.CrossEntropyLoss()

    # إنشاء سجل التدريب
    status = TrainingStatus.objects.create(training_type="full")

    epochs = 20
    for epoch in range(epochs):

        optimizer.zero_grad()
        preds = model(X)
        loss = loss_fn(preds, y)
        loss.backward()
        optimizer.step()

        # حساب الدقة
        correct = (preds.argmax(dim=1) == y).sum().item()
        accuracy = correct / len(y)

        # تحديث سجل التدريب
        status.progress = int((epoch + 1) / epochs * 100)
        status.loss = float(loss.item())
        status.accuracy = float(accuracy)
        status.save()

    # حفظ النموذج النهائي
    torch.save(model.state_dict(), "full_model.pt")

    return True

