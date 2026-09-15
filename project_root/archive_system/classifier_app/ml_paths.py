from pathlib import Path

from django.conf import settings


def get_projection_model_path():
    """
    النموذج الذاتي المشترك الحالي.
    موجود خارج archive_system داخل project_root/data
    """
    return (
        Path(settings.BASE_DIR).parent
        / "data"
        / "self_supervised_projection.pt"
    )


def get_domain_training_dir(domain):
    return (
        Path(settings.MEDIA_ROOT)
        / "training_exports"
        / f"domain_{domain.id}"
    )


def get_domain_training_file(domain):
    return (
        get_domain_training_dir(domain)
        / "manual_training_dataset.csv"
    )


def get_domain_model_dir(domain):
    return (
        Path(settings.MEDIA_ROOT)
        / "trained_models"
        / f"domain_{domain.id}"
    )


def get_domain_classifier_path(domain):
    return (
        get_domain_model_dir(domain)
        / "classifier_head.pkl"
    )


def get_domain_classifier_meta_path(domain):
    return (
        get_domain_model_dir(domain)
        / "classifier_meta.json"
    )

def get_domain_ocr_output_dir(domain):

    safe_domain = "".join(
        c if c.isalnum() or c in "-_ " else "_"
        for c in domain.title
    ).strip()

    return (
        Path(settings.BASE_DIR).parent
        / "data"
        / "ocr_output"
        / f"domain_{domain.id}_{safe_domain}"
    )
