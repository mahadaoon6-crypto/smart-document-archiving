import joblib
import numpy as np
import pandas as pd
from classifier_app.models import TrainingStatus
from sklearn.linear_model import LogisticRegression
import ast

def train_classifier_head():

    # قراءة ملف التدريب الجديد
    
    import os
    from django.conf import settings

    training_file = os.path.join(
        settings.MEDIA_ROOT,
        "training_exports",
        "manual_training_dataset.csv"
    )

    df = pd.read_csv(training_file)


    # تحويل عمود combined إلى مصفوفة NumPy
    X = np.array(df["combined"].apply(ast.literal_eval).tolist())

    # قراءة الفئات الصحيحة
    y = df["corrected_label"].tolist()

    # التحقق من وجود أكثر من فئة واحدة
    if len(set(y)) < 2:
        raise ValueError("لا يمكن تدريب طبقة التصنيف لأن ملف التدريب يحتوي فئة واحدة فقط.")

    # تدريب طبقة التصنيف
    clf = LogisticRegression(max_iter=3000)
    clf.fit(X, y)

    # حفظ النموذج
    joblib.dump(clf, "classifier_head.pkl")

    # تسجيل حالة التدريب
    TrainingStatus.objects.create(
        training_type="head",
        progress=100,
        loss=0,
        accuracy=0
    )

    return True
