from django.conf import settings
from django.db import models


class Well(models.Model):
    well_id = models.CharField(max_length=50, unique=True)
    owner_name = models.CharField(max_length=200, null=True, blank=True)
    location = models.CharField(max_length=200, null=True, blank=True)
    status = models.CharField(max_length=50, default="active")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Well {self.well_id}"


class Document(models.Model):

    # المشروع الذي تنتمي إليه الوثيقة
    domain = models.ForeignKey("TrainingDomain", on_delete=models.CASCADE, null=True, blank=True)

    # رقم السجل (رقم الإضبارة / رقم الموظف / رقم المعاملة)
    record_number = models.CharField(max_length=255, null=True, blank=True)

    # نوع الوثيقة (اختياري)
    doc_type = models.CharField(max_length=255, null=True, blank=True)
    index = models.ForeignKey("HumanIndex", on_delete=models.SET_NULL, null=True, blank=True)
    # الحقول القديمة التي لديك مسبقًا
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    ocr_text = models.TextField(null=True, blank=True)
    ocr_status = models.CharField(max_length=50, default="pending")
    classification_result = models.CharField(max_length=255, null=True, blank=True)
    classification_status = models.CharField(max_length=50, default="pending")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    # CAMeLBERT 768 + Projection 128 = 896
    combined_embedding = models.JSONField(
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.file_name} ({self.record_number})"

       
    class Meta:
        permissions = [
            ("can_view_dashboard", "Can view dashboard"),
            ("run_ocr", "Can run OCR"),
            ("classify_document", "Can classify document"),
        ]

    def __str__(self):
        return f"{self.dossier_type} - {self.file_name}"

class DocumentTimeline(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="timeline")
    action = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)

def __str__(self):
    return f"{self.document.id} - {self.action} - {self.timestamp}"


#=====================================
# إنشاء موديل التصحيح البشري
#======================================

class ManualIndex(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="manual_indexes")
    original_label = models.CharField(max_length=50)
    corrected_label = models.CharField(max_length=50)
    notes = models.TextField(blank=True, null=True)
    indexed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.document.id} - {self.corrected_label}"

#=====================================
# إنشاء جدول TrainingStatus
#======================================
class TrainingStatus(models.Model):
    training_type = models.CharField(max_length=50)  # head / full
    progress = models.IntegerField(default=0)
    loss = models.FloatField(null=True, blank=True)
    accuracy = models.FloatField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.training_type} - {self.progress}%"

#=====================================
# إنشاء جدول HumanIndexCategory
#======================================
class HumanIndexCategory(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    domain = models.CharField(max_length=200)  # مثل: معاملات مالية، عقود قانونية، ملفات هندسية
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.domain} - {self.name}"

#=====================================
# موديل مجال التدريب (موضوع الفهرسة)
#======================================
class TrainingDomain(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=False)

    # ⭐ الحقل الجديد
    is_trained = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

#=====================================
# موديل الفهارس البشرية
#======================================
class HumanIndex(models.Model):
    domain = models.ForeignKey(TrainingDomain, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    min_required = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.domain.title} - {self.name}"

#=====================================
# موديل وثائق التدريب
#======================================
class TrainingDocument(models.Model):
    domain = models.ForeignKey(TrainingDomain, on_delete=models.CASCADE)
    index = models.ForeignKey(HumanIndex, on_delete=models.CASCADE)
    file_name = models.CharField(max_length=200)
    file_path = models.CharField(max_length=500)
    ocr_text = models.TextField(null=True, blank=True)
    vector_text = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
)

    def __str__(self):
        return self.file_name


