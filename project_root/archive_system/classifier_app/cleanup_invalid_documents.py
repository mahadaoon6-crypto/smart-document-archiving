import os
from classifier_app.models import Document

def cleanup_invalid_documents():
    deleted_db = 0
    deleted_files = 0
    kept = 0

    for doc in Document.objects.all():
        try:
            # إذا لم يكن هناك مسار للملف → وثيقة غير صالحة
            if not doc.file_path:
                doc.delete()
                deleted_db += 1
                continue

            # إذا كان المسار غير موجود فعليًا → وثيقة غير صالحة
            if not os.path.exists(doc.file_path):
                doc.delete()
                deleted_db += 1
                continue

            # إذا كان اسم الملف في قاعدة البيانات لا يطابق اسم الملف الحقيقي
            real_name = os.path.basename(doc.file_path)
            if doc.file_name != real_name:
                # حذف الملف من المجلد
                try:
                    os.remove(doc.file_path)
                    deleted_files += 1
                except:
                    pass

                doc.delete()
                deleted_db += 1
                continue

            # إذا كان رقم السجل غير موجود في مسار المجلد
            if str(doc.record_number) not in doc.file_path:
                doc.delete()
                deleted_db += 1
                continue

            # إذا كان المشروع غير موجود في المسار
            if doc.domain and doc.domain.title not in doc.file_path:
                doc.delete()
                deleted_db += 1
                continue

            kept += 1

        except Exception as e:
            print(f"خطأ في الوثيقة {doc.id}: {e}")
            doc.delete()
            deleted_db += 1

    print(f"تم حذف {deleted_db} وثيقة غير صالحة من قاعدة البيانات.")
    print(f"تم حذف {deleted_files} ملف غير صالح من المجلدات.")
    print(f"تم الإبقاء على {kept} وثيقة سليمة.")
