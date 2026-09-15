import re
import shutil
from pathlib import Path

import joblib
import numpy as np
import torch

from django.conf import settings

from embeddings_module.extract_embeddings import extract_embeddings

from classifier_app.classifier import ProjectionHead
from classifier_app.ml_paths import (
    get_projection_model_path,
    get_domain_classifier_path,
)

from classifier_app.models import (
    HumanIndex,
    DocumentTimeline,
)

import csv
import json
from pathlib import Path

from classifier_app.ml_paths import (
    get_domain_ocr_output_dir,
)

def _safe_file_part(value):

    value = str(
        value or ""
    ).strip()

    # الأحرف الممنوعة في أسماء ملفات Windows
    for char in '<>:"/\\|?*':
        value = value.replace(
            char,
            "_"
        )

    return value or "unknown"

def save_document_representation(
    document,
    features=None,
    index=None
):


    # =====================================================
    # التحقق
    # =====================================================

    if document.domain is None:
        raise ValueError(
            "Document has no domain."
        )

    if (
        not document.ocr_text
        or not document.ocr_text.strip()
    ):
        raise ValueError(
            "Document has no OCR text."
        )

    # إذا لم يُمرر الفهرس نأخذه من الوثيقة
    if index is None:
        index = document.index

    if index is None:
        raise ValueError(
            "Document has no index."
        )

    # =====================================================
    # استخراج التمثيلات إذا لم تكن محسوبة مسبقًا
    # =====================================================

    if features is None:

        features = build_features(
            document.ocr_text
        )

    emb = np.asarray(
        features["emb"],
        dtype=np.float32
    )

    z = np.asarray(
        features["z"],
        dtype=np.float32
    )

    combined = np.asarray(
        features["combined"],
        dtype=np.float32
    )

    if combined.shape[0] != 896:
        raise ValueError(
            f"Expected 896 features, "
            f"got {combined.shape[0]}"
        )

    # =====================================================
    # 1. الحفظ في قاعدة البيانات
    # =====================================================

    document.combined_embedding = (
        combined.tolist()
    )

    document.save(
        update_fields=[
            "combined_embedding"
        ]
    )

    # =====================================================
    # 2. مجلد Domain
    # =====================================================

    output_dir = (
        get_domain_ocr_output_dir(
            document.domain
        )
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # =====================================================
    # اسم الملف
    #
    # رقم السجل - الفهرس - اسم الوثيقة.csv
    # =====================================================

    record_number = _safe_file_part(
        document.record_number
        or f"document_{document.id}"
    )

    index_name = _safe_file_part(
        index.name
    )

    document_name = Path(
        document.file_name
        or f"document_{document.id}"
    ).stem

    document_name = _safe_file_part(
        document_name
    )

    csv_name = (
        f"{record_number}-"
        f"{index_name}-"
        f"{document_name}.csv"
    )

    csv_path = (
        output_dir
        / csv_name
    )

    # =====================================================
    # محتوى CSV
    # =====================================================

    row = {

        "document_id":
            document.id,

        "domain_id":
            document.domain.id,

        "domain_title":
            document.domain.title,

        "record_number":
            document.record_number or "",

        "index_id":
            index.id,

        "index_name":
            index.name,

        "document_name":
            document.file_name,

        "ocr_text":
            document.ocr_text,

        # 768
        "emb":
            json.dumps(
                emb.tolist(),
                ensure_ascii=False
            ),

        # 128
        "z":
            json.dumps(
                z.tolist(),
                ensure_ascii=False
            ),

        # 896
        "combined":
            json.dumps(
                combined.tolist(),
                ensure_ascii=False
            ),
    }

    # =====================================================
    # الحفظ
    # =====================================================

    with open(
        csv_path,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=row.keys()
        )

        writer.writeheader()

        writer.writerow(
            row
        )

    return csv_path



# =========================================================
# الجهاز
# =========================================================

device = torch.device(
    "cuda" if torch.cuda.is_available() else "cpu"
)


# =========================================================
# Cache
# =========================================================

_projection_model = None

# الشكل:
# {
#   domain_id: {
#       "model": clf,
#       "mtime": timestamp
#   }
# }
_classifier_cache = {}


# =========================================================
# تحميل ProjectionHead
# =========================================================

def get_projection_model():

    global _projection_model

    if _projection_model is not None:
        return _projection_model

    projection_path = get_projection_model_path()

    if not projection_path.exists():
        raise FileNotFoundError(
            f"Projection model not found: {projection_path}"
        )

    model = ProjectionHead().to(device)

    state_dict = torch.load(
        projection_path,
        map_location=device
    )

    model.load_state_dict(state_dict)

    model.eval()

    _projection_model = model

    return _projection_model


# =========================================================
# تحميل Classifier الخاص بالـ Domain
# =========================================================

def get_classifier(domain):

    classifier_path = get_domain_classifier_path(domain)

    if not classifier_path.exists():
        raise FileNotFoundError(
            f"No classifier found for domain "
            f"{domain.id}: {classifier_path}"
        )

    modification_time = classifier_path.stat().st_mtime

    cached = _classifier_cache.get(domain.id)

    # إذا لم يتغير الملف نستخدم النسخة الموجودة بالذاكرة
    if (
        cached is not None
        and cached["mtime"] == modification_time
    ):
        return cached["model"]

    classifier = joblib.load(classifier_path)

    _classifier_cache[domain.id] = {
        "model": classifier,
        "mtime": modification_time,
    }

    return classifier


# =========================================================
# مسح Cache بعد إعادة التدريب
# =========================================================

def invalidate_classifier_cache(domain=None):

    if domain is None:
        _classifier_cache.clear()
        return

    _classifier_cache.pop(
        domain.id,
        None
    )


# =========================================================
# استخراج الميزات
#
# CAMeLBERT = 768
# Projection = 128
# Combined   = 896
# =========================================================

def build_features(text):

    if not text or not text.strip():
        raise ValueError("OCR text is empty.")

    # -----------------------------------------------------
    # 1. CAMeLBERT
    # -----------------------------------------------------

    embedding = extract_embeddings(text)

    emb = np.asarray(
        embedding,
        dtype=np.float32
    )

    if emb.ndim != 1:
        emb = emb.reshape(-1)

    if emb.shape[0] != 768:
        raise ValueError(
            "Invalid CAMeLBERT embedding size. "
            f"Expected 768, got {emb.shape[0]}."
        )

    # -----------------------------------------------------
    # 2. ProjectionHead
    # -----------------------------------------------------

    projection_model = get_projection_model()

    emb_tensor = (
        torch.from_numpy(emb)
        .unsqueeze(0)
        .to(device)
    )

    with torch.no_grad():

        z_tensor = projection_model(
            emb_tensor
        )

    z = (
        z_tensor
        .squeeze(0)
        .cpu()
        .numpy()
        .astype(np.float32)
    )

    if z.shape[0] != 128:
        raise ValueError(
            "Invalid ProjectionHead output size. "
            f"Expected 128, got {z.shape[0]}."
        )

    # -----------------------------------------------------
    # 3. Combined
    # -----------------------------------------------------

    combined = np.concatenate(
        [emb, z]
    ).astype(np.float32)

    if combined.shape[0] != 896:
        raise ValueError(
            "Invalid combined feature size. "
            f"Expected 896, got {combined.shape[0]}."
        )

    return {
        "emb": emb,
        "z": z,
        "combined": combined,
    }


# =========================================================
# اختصار عند الحاجة فقط للـ combined
# =========================================================

def create_combined_embedding(text):

    return build_features(
        text
    )["combined"]


# =========================================================
# تصنيف النص
# =========================================================

def classify_text(text, domain):

    if domain is None:
        return {
            "success": False,
            "label": None,
            "confidence": None,
            "error": "No domain was provided."
        }

    if not domain.is_trained:
        return {
            "success": False,
            "label": None,
            "confidence": None,
            "error": "Domain is not trained."
        }

    try:

        features = build_features(text)

        combined = features["combined"]

        X = combined.reshape(
            1,
            -1
        )

        classifier = get_classifier(domain)

        # حماية إضافية
        expected_features = getattr(
            classifier,
            "n_features_in_",
            None
        )

        if (
            expected_features is not None
            and expected_features != 896
        ):
            raise ValueError(
                "Classifier has incompatible input size: "
                f"{expected_features}. Expected 896."
            )

        prediction = classifier.predict(
            X
        )[0]

        confidence = None

        if hasattr(
            classifier,
            "predict_proba"
        ):

            probabilities = (
                classifier.predict_proba(X)[0]
            )

            confidence = float(
                np.max(probabilities)
            )

        return {
            "success": True,
            "label": str(prediction),
            "confidence": confidence,
            "error": None,
        }

    except Exception as exc:

        return {
            "success": False,
            "label": None,
            "confidence": None,
            "error": str(exc),
        }


# =========================================================
# تنظيف اسم المجلد فقط
# لا علاقة له بتنظيف نص OCR
# =========================================================

def _safe_folder_name(value):

    value = str(
        value or ""
    ).strip()

    value = re.sub(
        r'[<>:"/\\|?*]',
        "_",
        value
    )

    return value or "unknown"


# =========================================================
# تحديد المسار الحالي للملف
# =========================================================

def _get_source_file_path(document):

    if not document.file_path:
        return None

    path = Path(
        document.file_path
    )

    if path.is_absolute():
        return path

    return (
        Path(settings.MEDIA_ROOT)
        / path
    )


# =========================================================
# نقل الوثيقة إلى مجلد الفهرس المتوقع
#
# media/
#   Domain/
#       record_number/
#           HumanIndex/
#               file
# =========================================================

def move_document_to_index_folder(
    document,
    predicted_index
):

    source_path = _get_source_file_path(
        document
    )

    if (
        source_path is None
        or not source_path.exists()
    ):
        # لا نفشل التصنيف بسبب مشكلة نقل الملف
        return None

    domain_folder = _safe_folder_name(
        document.domain.title
    )

    record_folder = _safe_folder_name(
        document.record_number
        or f"document_{document.id}"
    )

    index_folder = _safe_folder_name(
        predicted_index.name
    )

    target_dir = (
        Path(settings.MEDIA_ROOT)
        / domain_folder
        / record_folder
        / index_folder
    )

    target_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    original_name = (
        document.file_name
        or source_path.name
    )

    target_path = (
        target_dir
        / original_name
    )

    # منع الكتابة فوق ملف موجود
    if (
        target_path.exists()
        and target_path.resolve()
        != source_path.resolve()
    ):

        target_path = (
            target_dir
            / (
                f"{target_path.stem}"
                f"_{document.id}"
                f"{target_path.suffix}"
            )
        )

    # الملف موجود أصلًا في المكان الصحيح
    if (
        source_path.resolve()
        != target_path.resolve()
    ):

        shutil.move(
            str(source_path),
            str(target_path)
        )

    # نحافظ على أسلوب التخزين القديم:
    # إذا كان file_path مطلقًا يبقى مطلقًا
    if Path(document.file_path).is_absolute():

        document.file_path = str(
            target_path
        )

    else:

        document.file_path = str(
            target_path.relative_to(
                Path(settings.MEDIA_ROOT)
            )
        )

    document.save(
        update_fields=[
            "file_path"
        ]
    )

    return target_path


# =========================================================
# تصنيف Document كامل
# =========================================================

def classify_document(
    document,
    move_file=True
):

    # =====================================================
    # التحقق من OCR
    # =====================================================

    if (
        not document.ocr_text
        or not document.ocr_text.strip()
    ):

        document.classification_status = (
            "failed"
        )

        document.save(
            update_fields=[
                "classification_status"
            ]
        )

        return {
            "success": False,
            "error": "Document has no OCR text."
        }

    # =====================================================
    # Domain
    # =====================================================

    if document.domain is None:

        document.classification_status = (
            "failed"
        )

        document.save(
            update_fields=[
                "classification_status"
            ]
        )

        return {
            "success": False,
            "error": "Document has no domain."
        }

    # =====================================================
    # التدريب
    # =====================================================

    if not document.domain.is_trained:

        document.classification_status = (
            "pending"
        )

        document.save(
            update_fields=[
                "classification_status"
            ]
        )

        return {
            "success": False,
            "error": "Domain is not trained."
        }

    document.classification_status = (
        "processing"
    )

    document.save(
        update_fields=[
            "classification_status"
        ]
    )

    try:

        # =================================================
        # 1. إنشاء الميزات مرة واحدة فقط
        # =================================================

        features = build_features(
            document.ocr_text
        )

        combined = (
            features["combined"]
        )

        # =================================================
        # 2. classifier الخاص بالـDomain
        # =================================================

        classifier = get_classifier(
            document.domain
        )

        X = combined.reshape(
            1,
            -1
        )

        prediction = (
            classifier.predict(X)[0]
        )

        predicted_label = str(
            prediction
        )

        # =================================================
        # 3. Confidence
        # =================================================

        confidence = None

        if hasattr(
            classifier,
            "predict_proba"
        ):

            probabilities = (
                classifier
                .predict_proba(X)[0]
            )

            confidence = float(
                np.max(probabilities)
            )

        # =================================================
        # 4. HumanIndex
        # =================================================

        predicted_index = (
            HumanIndex.objects
            .filter(
                domain=document.domain,
                name=predicted_label
            )
            .first()
        )

        if predicted_index is None:

            document.classification_result = (
                predicted_label
            )

            document.classification_status = (
                "failed"
            )
            document.save(
                update_fields=[
                    "classification_result",
                    "classification_status"
                ]
            )

            return {
                "success": False,
                "prediction":
                    predicted_label,
                "confidence":
                    confidence,
                "error":
                    "Predicted HumanIndex "
                    "does not exist."
            }

        # =================================================
        # 5. حفظ نتيجة التصنيف
        # =================================================

        document.index = (
            predicted_index
        )

        document.classification_result = (
            predicted_index.name
        )

        document.classification_status = (
            "done"
        )

        document.save(
            update_fields=[
                "index",
                "classification_result",
                "classification_status"
            ]
        )

        # =================================================
        # 6. ⭐️ حفظ التمثيل في DB + CSV
        # =================================================

        csv_path = (
            save_document_representation(
                document=document,
                features=features,
                index=predicted_index
            )
        )

        # =================================================
        # 7. نقل الملف الأصلي
        # =================================================

        moved_to = None

        if move_file:

            moved_to = (
                move_document_to_index_folder(
                    document,
                    predicted_index
                )
            )

        return {
            "success": True,

            "label":
                predicted_index.name,

            "index_id":
                predicted_index.id,

            "confidence":
                confidence,

            "csv_path":
                str(csv_path),

            "file_path":
                (
                    str(moved_to)
                    if moved_to
                    else document.file_path
                ),
        }

    except Exception as exc:

        document.classification_status = (
            "failed"
        )

        document.save(
            update_fields=[
                "classification_status"
            ]
        )

        return {
            "success": False,
            "error": str(exc)
        }

