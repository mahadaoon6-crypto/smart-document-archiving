from django.urls import path
from . import views
from .views import archive_view, dossier_detail_view, document_detail_view
from .views import classification_report_view   # ← هذا هو السطر المطلوب


from .user_management_views import user_management_view
from .user_permissions_view import user_permissions_view
from dashboard import views as dashboard_views

# ⭐ استيراد الدالة الصحيحة من classifier_app
from classifier_app.manual_training_export import export_manual_training_dataset

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),

    # صفحة تفاصيل الوثيقة
    path('document/<int:document_id>/', views.document_detail_view, name='document_detail'),

    path("documents/", views.documents_list_view, name="documents_list"),

    path("upload/", views.upload_document_view, name="upload_document"),
    
    # روابط خاصة بالوثيقة
    path('document/<int:document_id>/rerun_ocr/', views.rerun_ocr_view, name='rerun_ocr'),
    path('document/<int:document_id>/rerun_classification/', views.rerun_classification_view, name='rerun_classification'),
    path("document/<int:document_id>/report/", views.classification_report_view, name="classification_report"),


    path("document/view/<int:document_id>/", views.view_document, name="view_document"),

    # روابط التصحيح والقبول
    path("document/<int:document_id>/accept/", views.accept_classification, name="accept_classification"),
    path("document/<int:document_id>/correct/", views.correct_classification, name="correct_classification"),

    # زر إنشاء ملف التدريب
    path("model/generate-training-file/", dashboard_views.generate_training_file_view, name="generate_training_file"),

    path("users/", user_management_view, name="user_management"),
    path("permissions/", user_permissions_view, name="user_permissions"),
    path("document/<int:document_id>/manual/", views.manual_index_view, name="manual_index"),

    path("export/manual_training/", export_manual_training_dataset, name="export_manual_training"),

    path("manual/index/list/", views.manual_index_list_view, name="manual_index_list"),
    path("model/training/", views.model_training_page, name="model_training_page"),

    path("model/train/head/", views.train_classifier_head_view, name="train_classifier_head"),
    path("model/train/full/", views.train_full_model_view, name="train_full_model"),

    path("training/manage/", views.manage_training_page, name="manage_training_page"),
    path("training/index/edit/<int:pk>/", views.edit_index, name="edit_index"),
    path("training/index/delete/<int:pk>/", views.delete_index, name="delete_index"),

    path("domains/", views.manage_domains_view, name="manage_domains"),
    path("domains/activate/<int:domain_id>/", views.activate_domain_view, name="activate_domain"),
    path("domains/create/", views.create_domain_view, name="create_domain"),
    path("domains/delete/<int:domain_id>/", views.delete_domain, name="delete_domain"),
    #path("document/<int:document_id>/", views.document_detail_view, name="document_detail"),
    path("document/<int:document_id>/", views.document_detail_view, name="document_detail_view"),

    
    path("human-indexes/", views.manage_human_indexes, name="manage_human_indexes"),
    path("indexes/create/<int:domain_id>/", views.create_index, name="create_index"),
    path("indexes/edit/<int:pk>/", views.edit_index, name="edit_index"),
    path("indexes/delete/<int:pk>/", views.delete_index, name="delete_index"),
    path("archive/", views.archive_view, name="archive_view"),
    path("archive/dossier/<str:record_number>/", views.dossier_detail_view, name="dossier_detail_view"),
   
    #path("archive/document/<int:doc_id>/", document_detail_view, name="document_detail_view"),

    path("archive/document/<int:document_id>/", views.document_detail_view, name="document_detail_view"),

    path(
    "document/rerun/<int:document_id>/",
    views.rerun_classification_view,
    name="rerun_classification_view"
),

    # باقي الروابط الموجودة لديك

    path(
        "documents/<int:document_id>/view/",
        views.document_viewer,
        name="document_viewer"
    ),

    path(
        "documents/<int:document_id>/file/",
        views.document_file_view,
        name="document_file"
    ),


]
