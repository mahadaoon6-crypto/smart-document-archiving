from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from classifier_app.models import Document

def setup_permissions():
    # إنشاء المجموعات
    admin_group, _ = Group.objects.get_or_create(name="admin")
    staff_group, _ = Group.objects.get_or_create(name="staff")
    viewer_group, _ = Group.objects.get_or_create(name="viewer")

    # نوع المحتوى
    doc_type = ContentType.objects.get_for_model(Document)

    # الصلاحيات
    perm_view = Permission.objects.get(codename="view_document", content_type=doc_type)
    perm_add = Permission.objects.get(codename="add_document", content_type=doc_type)
    perm_change = Permission.objects.get(codename="change_document", content_type=doc_type)
    perm_delete = Permission.objects.get(codename="delete_document", content_type=doc_type)

    # صلاحيات إضافية مخصصة
    # يمكنك لاحقًا إنشاء صلاحيات مخصصة مثل run_ocr أو classify_document

    # ربط الصلاحيات بالمجموعات
    admin_group.permissions.set([perm_view, perm_add, perm_change, perm_delete])
    staff_group.permissions.set([perm_view, perm_add])
    viewer_group.permissions.set([perm_view])
