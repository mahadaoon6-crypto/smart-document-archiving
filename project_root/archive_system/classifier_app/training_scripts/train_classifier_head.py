import ast
import json

import joblib
import numpy as np
import pandas as pd

from django.utils import timezone

from sklearn.linear_model import (
    LogisticRegression,
)

from classifier_app.models import (
    TrainingStatus,
    TrainingDomain,
    HumanIndex,
)

from classifier_app.ml_paths import (
    get_domain_training_file,
    get_domain_classifier_path,
    get_domain_classifier_meta_path,
)


def train_classifier_head(
    domain=None
):

    # =====================================================
    # الحصول على Domain
    # =====================================================

    if domain is None:

        domain = (
            TrainingDomain.objects
            .filter(is_active=True)
            .first()
        )

    if domain is None:

        raise ValueError(
            "لا يوجد مشروع مفعل للتدريب."
        )

    # =====================================================
    # ملف التدريب
    # =====================================================

    training_file = (
        get_domain_training_file(
            domain
        )
    )

    if not training_file.exists():

        raise FileNotFoundError(
            "ملف التدريب غير موجود. "
            "قم أولًا بإنشاء ملف التدريب: "
            f"{training_file}"
        )

    # =====================================================
    # قراءة Dataset
    # =====================================================

    df = pd.read_csv(
        training_file
    )

    required_columns = {
        "combined",
        "corrected_label",
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:

        raise ValueError(
            "ملف التدريب ناقص الأعمدة التالية: "
            + ", ".join(
                sorted(missing_columns)
            )
        )

    # =====================================================
    # إزالة الصفوف الفارغة
    # =====================================================

    df = df.dropna(
        subset=[
            "combined",
            "corrected_label",
        ]
    ).copy()

    if df.empty:

        raise ValueError(
            "ملف التدريب لا يحتوي "
            "على بيانات صالحة."
        )

    # =====================================================
    # تحويل combined
    # =====================================================

    vectors = []

    labels = []

    bad_rows = []

    for row_index, row in df.iterrows():

        try:

            combined = row[
                "combined"
            ]

            if isinstance(
                combined,
                str
            ):

                combined = (
                    ast.literal_eval(
                        combined
                    )
                )

            vector = np.asarray(
                combined,
                dtype=np.float32
            ).reshape(-1)

            if vector.shape[0] != 896:

                raise ValueError(
                    "Expected 896 features, "
                    f"got {vector.shape[0]}"
                )

            label = str(
                row[
                    "corrected_label"
                ]
            ).strip()

            if not label:

                raise ValueError(
                    "Empty label"
                )

            vectors.append(
                vector
            )

            labels.append(
                label
            )

        except Exception as exc:

            bad_rows.append(
                (
                    row_index,
                    str(exc)
                )
            )

    if not vectors:

        raise ValueError(
            "لا توجد صفوف تدريب صالحة."
        )

    X = np.vstack(
        vectors
    ).astype(
        np.float32
    )

    y = np.asarray(
        labels
    )

    # =====================================================
    # التحقق من الفئات
    # =====================================================

    unique_labels = sorted(
        set(labels)
    )

    if len(unique_labels) < 2:

        raise ValueError(
            "لا يمكن تدريب طبقة التصنيف "
            "لأن البيانات تحتوي فئة واحدة فقط."
        )

    # =====================================================
    # التحقق أن الفئات موجودة داخل Domain
    # =====================================================

    valid_index_names = set(
        HumanIndex.objects
        .filter(
            domain=domain
        )
        .values_list(
            "name",
            flat=True
        )
    )

    unknown_labels = (
        set(unique_labels)
        - valid_index_names
    )

    if unknown_labels:

        raise ValueError(
            "ملف التدريب يحتوي فئات "
            "غير موجودة داخل المشروع: "
            + ", ".join(
                sorted(
                    unknown_labels
                )
            )
        )

    # =====================================================
    # تدريب Logistic Regression
    #
    # class_weight balanced مهم عند اختلاف
    # عدد الوثائق بين الفهارس
    # =====================================================

    clf = LogisticRegression(
        max_iter=3000,
        class_weight="balanced",
        random_state=42,
    )

    clf.fit(
        X,
        y
    )

    # =====================================================
    # Accuracy على بيانات التدريب
    #
    # هذه ليست Test Accuracy.
    # فقط مؤشر داخلي.
    # =====================================================

    training_accuracy = float(
        clf.score(
            X,
            y
        )
    )

    # =====================================================
    # حفظ النموذج الخاص بالـ Domain
    # =====================================================

    classifier_path = (
        get_domain_classifier_path(
            domain
        )
    )

    classifier_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    joblib.dump(
        clf,
        classifier_path
    )

    # =====================================================
    # حفظ Metadata
    # =====================================================

    meta_path = (
        get_domain_classifier_meta_path(
            domain
        )
    )

    metadata = {
        "domain_id": domain.id,
        "domain_title": domain.title,
        "classes": (
            clf.classes_.tolist()
        ),
        "n_features": int(
            clf.n_features_in_
        ),
        "training_records": int(
            len(X)
        ),
        "training_accuracy": (
            training_accuracy
        ),
        "ignored_rows": int(
            len(bad_rows)
        ),
        "trained_at": (
            timezone.now()
            .isoformat()
        ),
    }

    with open(
        meta_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            metadata,
            file,
            ensure_ascii=False,
            indent=2
        )

    # =====================================================
    # المشروع أصبح مدربًا
    # =====================================================

    domain.is_trained = True

    domain.save(
        update_fields=[
            "is_trained"
        ]
    )

    # =====================================================
    # Training Status
    # =====================================================

    TrainingStatus.objects.create(
        training_type="head",
        progress=100,
        loss=0,
        accuracy=training_accuracy
    )

    # =====================================================
    # Cache
    # =====================================================

    # Import هنا لمنع الاعتماد المتبادل عند import
    from classifier_app.classifier_service import (
        invalidate_classifier_cache,
    )

    invalidate_classifier_cache(
        domain
    )

    # =====================================================
    # Result
    # =====================================================

    return {
        "success": True,
        "domain_id": domain.id,
        "domain_title": domain.title,
        "classifier_path": str(
            classifier_path
        ),
        "classes": (
            clf.classes_.tolist()
        ),
        "records": int(
            len(X)
        ),
        "training_accuracy": (
            training_accuracy
        ),
        "ignored_rows": (
            len(bad_rows)
        ),
    }

