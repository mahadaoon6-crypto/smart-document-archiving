from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from classifier_app.models import Well, Document, DocumentTimeline, ManualIndex
from .forms import DocumentUploadForm
import os

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from classifier_app.classifier_service import classify_document

from pathlib import Path
import mimetypes

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render

from classifier_app.models import Document
@login_required
def document_file_view(request, document_id):

    document = get_object_or_404(
        Document,
        id=document_id
    )

    if not document.file_path:
        raise Http404("لا يوجد ملف مرتبط بهذه الوثيقة.")

    file_path = Path(document.file_path)

    # إذا كان المسار مخزنًا نسبيًا
    if not file_path.is_absolute():
        file_path = (
            Path(settings.MEDIA_ROOT)
            / file_path
        )

    if not file_path.exists():
        raise Http404(
            f"الملف غير موجود: {file_path}"
        )

    # تحديد نوع الملف
    content_type, _ = mimetypes.guess_type(
        str(file_path)
    )

    if not content_type:
        content_type = "application/octet-stream"

    return FileResponse(
        open(file_path, "rb"),
        content_type=content_type,
        as_attachment=False
    )


# ---------------------------------------------------------
# دالة صفحة عرض الوثيقة
# ---------------------------------------------------------

@login_required
def document_viewer(request, document_id):

    document = get_object_or_404(
        Document,
        id=document_id
    )

    return render(
        request,
        "classifier_app/document_viewer.html",
        {
            "document": document
        }
    )


# ---------------------------------------------------------
# دالة لتصفية ناتج OCR قبل حفظه
# ---------------------------------------------------------
def clean_ocr_output(text):
    if isinstance(text, dict):
        return text.get("text", "")
    if isinstance(text, list):
        return "\n".join([str(t) for t in text])
    return str(text)


# ---------------------------------------------------------
@login_required
@permission_required("classifier_app.can_view_dashboard", raise_exception=True)
def manual_index_list_view(request):
    items = ManualIndex.objects.select_related("document").order_by("-timestamp")
    return render(request, "dashboard/manual_index_list.html", {"items": items})

# ---------------------------------------------------------
# لوحة التحكم (معدّلة للعمل على المجال الفعّال)
# ---------------------------------------------------------
from classifier_app.models import ManualIndex, TrainingDomain, HumanIndex

@login_required
@permission_required("classifier_app.can_view_dashboard", raise_exception=True)
def dashboard_view(request):

    #---------------------------------------------
    # الحصول على المجال الفعّال
    #---------------------------------------------
    active_domain = TrainingDomain.objects.filter(is_active=True).first()
    indexes = HumanIndex.objects.filter(domain=active_domain)

    if not active_domain:
        messages.error(request, "لا يوجد مشروع مفعل للأرشفة.")
        return render(request, "dashboard/dashboard.html", {
            "active_domain": None,
            "indexes": [],
            "documents": [],
            "total_docs": 0,
            "ocr_done": 0,
            "ocr_pending": 0,
            "classify_done": 0,
            "classify_pending": 0,
            "need_review": 0,
            "manual_count": 0,
            "can_add_document": request.user.has_perm('classifier_app.add_document'),
        })

    #---------------------------------------------
    # جلب الفهارس الخاصة بالمجال الفعّال
    #---------------------------------------------
    indexes = HumanIndex.objects.filter(domain=active_domain)

    #---------------------------------------------
    # جلب الوثائق الخاصة بالمجال الفعّال
    #---------------------------------------------
    documents = Document.objects.filter(classification_result__in=[idx.name for idx in indexes]).order_by('-uploaded_at')

    #---------------------------------------------
    # إحصائيات الوثائق
    #---------------------------------------------
    total_docs = documents.count()
    ocr_done = documents.filter(ocr_status="done").count()
    ocr_pending = documents.filter(ocr_status="pending").count()
    classify_done = documents.filter(classification_status="done").count()
    classify_pending = documents.filter(classification_status="pending").count()

    # وثائق تحتاج إشراف بشري
    need_review = documents.filter(classification_status="pending").count()

    # عدد التصحيحات البشرية الخاصة بالمجال الفعّال
    manual_count = ManualIndex.objects.filter(corrected_label__in=[idx.name for idx in indexes]).count()

    context = {
        "active_domain": active_domain,
        "indexes": indexes,
        "documents": documents[:10],   # عرض آخر 10 وثائق فقط
        "total_docs": total_docs,
        "ocr_done": ocr_done,
        "ocr_pending": ocr_pending,
        "classify_done": classify_done,
        "classify_pending": classify_pending,
        "need_review": need_review,
        "manual_count": manual_count,
        "can_add_document": request.user.has_perm('classifier_app.add_document'),
    }

    return render(request, "dashboard/dashboard.html", context)



# ---------------------------------------------------------
# إعادة تشغيل OCR + Timeline
# ---------------------------------------------------------
from ocr_module.ocr_engine import run_ocr_on_image

@login_required
@permission_required("classifier_app.run_ocr", raise_exception=True)
def rerun_ocr_view(request, document_id):
    document = get_object_or_404(Document, id=document_id)

    raw_text = run_ocr_on_image(document.file_path)
    text = clean_ocr_output(raw_text)

    ocr_text_file = document.file_path + ".txt"
    with open(ocr_text_file, "w", encoding="utf-8") as f:
        f.write(text)

    document.ocr_text = text
    document.ocr_status = "done" if text.strip() else "error"
    document.save()

    DocumentTimeline.objects.create(
        document=document,
        action="إعادة تشغيل OCR"
    )

    messages.success(request, "✔️ تم تشغيل OCR مرة أخرى بنجاح")

    return redirect("document_detail", document_id=document.id)

from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from classifier_app.models import Document, TrainingDomain, HumanIndex, DocumentTimeline
from classifier_app.classifier_service import classify_document
import os

@login_required
@permission_required("classifier_app.classify_document", raise_exception=True)
def rerun_classification_view(request, document_id):
    document = get_object_or_404(Document, id=document_id)

    # قراءة النص
    ocr_text_file = document.file_path + ".txt"
    if os.path.exists(ocr_text_file):
        with open(ocr_text_file, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = document.ocr_text or ""

    if not text.strip():
        document.classification_result = "لا يوجد نص كافٍ للتصنيف"
        document.classification_status = "error"
        document.save()
        return redirect("document_detail", document_id=document.id)

    # الحصول على المجال الفعّال
    active_domain = (
        TrainingDomain.objects
        .filter(is_active=True)
        .first()
    )

    if not active_domain:

        messages.error(
            request,
            "لا يوجد مشروع مفعل."
        )

        return redirect(
            "model_training_page"
        )

    try:

        result = train_classifier_head(
            active_domain
        )

        classes = ", ".join(
            result["classes"]
        )

        messages.success(
            request,
            (
                "✔️ تم تدريب طبقة التصنيف بنجاح. "
                f"السجلات: {result['records']} | "
                f"الفئات: {classes} | "
                f"Training accuracy: "
                f"{result['training_accuracy'] * 100:.2f}%"
            )
        )

    except Exception as exc:

        messages.error(
            request,
            f"فشل تدريب النموذج: {exc}"
        )

    return redirect(
        "model_training_page"
    )



def train_classifier_head_view(request):

    active_domain = (
        TrainingDomain.objects
        .filter(is_active=True)
        .first()
    )

    if not active_domain:

        messages.error(
            request,
            "لا يوجد مشروع مفعل."
        )

        return redirect(
            "model_training_page"
        )

    try:

        result = train_classifier_head(
            active_domain
        )

        classes = ", ".join(
            result["classes"]
        )

        messages.success(
            request,
            (
                "✔️ تم تدريب طبقة التصنيف بنجاح. "
                f"السجلات: {result['records']} | "
                f"الفئات: {classes} | "
                f"Training accuracy: "
                f"{result['training_accuracy'] * 100:.2f}%"
            )
        )

    except Exception as exc:

        messages.error(
            request,
            f"فشل تدريب النموذج: {exc}"
        )

    return redirect(
        "model_training_page"
    )



from django.shortcuts import render, redirect
from django.contrib import messages
from classifier_app.models import Document, TrainingDomain, HumanIndex
from classifier_app.classifier_service import (
    classify_document,
    build_features
)

@login_required
@permission_required("classifier_app.view_document", raise_exception=True)
def classification_report_view(request, document_id):
    document = Document.objects.get(id=document_id)

    text = (document.ocr_text or "").strip()

    # إذا النص فارغ
    if not text:
        result = "لا يوجد نص OCR"
        confidence = None
        emb = []
        z = []
        combined = []
    else:
        # استخراج التمثيلات العددية
        try:
            features = build_features(text)
            emb = features["emb"]
            z = features["z"]
            combined = features["combined"]
        except Exception as exc:
            emb = []
            z = []
            combined = []
            messages.error(request, f"فشل استخراج التمثيل العددي: {exc}")

        # تشغيل التصنيف
        classification = classify_document(document, move_file=False)

        if classification["success"]:
            result = classification["label"]
            confidence = classification.get("confidence")
        else:
            result = classification.get("error", "فشل التصنيف")
            confidence = None

    context = {
        "document": document,
        "text": text,
        "result": result,
        "confidence": confidence,
        "emb": emb,
        "z": z,
        "combined": combined,
    }

    return render(request, "dashboard/classification_report.html", context)


# ---------------------------------------------------------
# تسجيل الدخول
# ---------------------------------------------------------
from django.contrib.messages import get_messages
def login_view(request):
    # تنظيف الرسائل القديمة
    storage = get_messages(request)
    for _ in storage:
        pass
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect("dashboard")
        else:
            messages.error(request, "اسم المستخدم أو كلمة المرور غير صحيحة")

    return render(request, "dashboard/login.html")


# ---------------------------------------------------------
# تسجيل الخروج
# ---------------------------------------------------------
def logout_view(request):
    logout(request)
    return redirect("login")

#--------------------------------------
# دالة الفهرسة اليدوية (معدّلة للعمل على المجال الفعّال)
#--------------------------------------
@login_required
@permission_required("classifier_app.view_document", raise_exception=True)
def manual_index_view(request, document_id):
    from classifier_app.models import TrainingDomain, HumanIndex

    document = get_object_or_404(Document, id=document_id)

    # قراءة النص
    ocr_text_file = document.file_path + ".txt"
    if os.path.exists(ocr_text_file):
        with open(ocr_text_file, "r", encoding="utf-8") as f:
            ocr_text = f.read()
    else:
        ocr_text = document.ocr_text or ""

    #---------------------------------------------
    # الحصول على المجال الفعّال
    #---------------------------------------------
    active_domain = TrainingDomain.objects.filter(is_active=True).first()
    if not active_domain:
        messages.error(request, "لا يوجد مشروع مفعل للتصنيف.")
        return redirect("document_detail", document_id=document.id)

    #---------------------------------------------
    # الحصول على فهارس المجال الفعّال
    #---------------------------------------------
    indexes = HumanIndex.objects.filter(domain=active_domain)

    if request.method == "POST":
        corrected_label = request.POST.get("corrected_label")
        notes = request.POST.get("notes", "")

        # التحقق أن الفهرس المختار ينتمي للمجال الفعّال
        valid_labels = [idx.name for idx in indexes]
        if corrected_label not in valid_labels:
            messages.error(request, "الفهرس المختار لا ينتمي للمجال الفعّال.")
            return redirect("manual_index", document_id=document.id)

        # حفظ التصحيح
        ManualIndex.objects.create(
            document=document,
            original_label=document.classification_result,
            corrected_label=corrected_label,
            notes=notes,
            indexed_by=request.user
        )

        # تحديث الوثيقة
        document.classification_result = corrected_label
        document.classification_status = "corrected"
        document.save()

        # إضافة إلى السجل الزمني
        DocumentTimeline.objects.create(
            document=document,
            action=f"تصحيح بشري للتصنيف — النتيجة الجديدة: {corrected_label}"
        )

        messages.success(request, f"✔️ تم حفظ التصحيح البشري — النتيجة الجديدة: {corrected_label}")

        return redirect("document_detail", document_id=document.id)

    return render(request, "dashboard/manual_index.html", {
        "document": document,
        "ocr_text": ocr_text,
        "indexes": indexes,  # نرسل الفهارس الجديدة للقالب
    })





#---------------------------------------------
#دالة التدريب 
#---------------------------------------------
from classifier_app.models import TrainingStatus
@login_required
@permission_required("classifier_app.can_view_dashboard", raise_exception=True)

def model_training_view(request):
    status = TrainingStatus.objects.order_by("-timestamp").first()

    return render(request, "dashboard/model_training.html", {
        "training_status": status,
        "manual_count": ManualIndex.objects.count(),
        "training_log": DocumentTimeline.objects.filter(action__contains="تدريب"),
        "last_training": status.timestamp if status else "لم يتم التدريب بعد",
    })


@login_required
def train_classifier_head_view(request):
    from classifier_app.training_scripts.train_classifier_head import train_classifier_head
    from classifier_app.models import TrainingDomain
    from django.contrib import messages

    messages.info(request, "⏳ بدأ تدريب طبقة التصنيف… يرجى الانتظار حتى انتهاء العملية.")

    try:
        # تنفيذ التدريب
        train_classifier_head()
        messages.success(request, "تم تدريب طبقة التصنيف بنجاح 🧠")

        # الحصول على المشروع الفعّال
        active_domain = TrainingDomain.objects.filter(is_active=True).first()

        # تعطيل جميع المجالات الأخرى
        TrainingDomain.objects.update(is_active=False)

        # إعادة تفعيل المشروع الفعّال
        active_domain.is_active = True

        # ⭐ إضافة علامة أن النموذج مدرّب
        active_domain.is_trained = True

        active_domain.save()

        messages.success(
            request,
            "✔ تم تفعيل هذا المشروع كنظام الأرشفة الأساسي."
        )

    except ValueError:
        messages.error(
            request,
            "لا يمكن تدريب طبقة التصنيف لأن ملف التدريب يحتوي فئة واحدة فقط."
        )
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء التدريب: {str(e)}")

    return redirect("model_training_page")

#---------------------------------------------
# دالة تدريب النموذج كاملًا
#---------------------------------------------
@login_required
def train_full_model_view(request):
    messages.info(
        request,
        "⚠ تدريب النموذج كاملًا يحتاج وقتًا أطول، ويُستخدم لتطوير المشروع وتحديث النموذج بشكل شامل."
    )

    from classifier_app.training_scripts.train_full_model import train_full_model
    from classifier_app.models import TrainingDomain
    from django.contrib import messages

    try:
        train_full_model()
        messages.success(request, "تم تدريب النموذج كاملًا بنجاح 🔥")

        domain = TrainingDomain.objects.first()
        TrainingDomain.objects.update(is_active=False)

        domain.is_active = True
        domain.save()

        messages.success(
            request,
            "✔ تم تفعيل هذا المشروع كنظام الأرشفة الأساسي. سيتم استخدام فهارسه في جميع عمليات التصنيف الآلي."
        )

    except ValueError:
        messages.error(
            request,
            "لا يمكن تدريب النموذج لأن ملف التدريب يحتوي فئة واحدة فقط. "
            "أضيفي أمثلة من فئات أخرى ثم أعيدي المحاولة."
        )
    except Exception as e:
        messages.error(request, f"حدث خطأ أثناء التدريب: {str(e)}")

    return redirect("model_training")



#---------------------------------------------
# عرض الفهارس + إضافة فهرس جديد
#---------------------------------------------
@login_required
def manage_human_indexes(request):
    from classifier_app.models import TrainingDomain, HumanIndex

    active_domain = TrainingDomain.objects.filter(is_active=True).first()
    indexes = HumanIndex.objects.filter(domain=active_domain)

    return render(request, "dashboard/manage_human_indexes.html", {
        "active_domain": active_domain,
        "indexes": indexes,
    })




#---------------------------------------------
#  بشري تعديل فهرس
#---------------------------------------------
@login_required
def edit_human_index(request, pk):
    from classifier_app.models import HumanIndexCategory
    from django.contrib import messages

    cat = HumanIndexCategory.objects.get(id=pk)

    if request.method == "POST":
        cat.name = request.POST.get("name")
        cat.domain = request.POST.get("domain")
        cat.description = request.POST.get("description")
        cat.save()
        messages.success(request, "تم تعديل الفهرس بنجاح.")
        return redirect("manage_human_index_categories")

    return render(request, "dashboard/edit_human_index.html", {"cat": cat})
#---------------------------------------------
#   تعديل فهرس المشروع
#---------------------------------------------
@login_required
def edit_index(request, pk):
    from classifier_app.models import HumanIndex

    index = HumanIndex.objects.get(pk=pk)

    if request.method == "POST":
        index.name = request.POST.get("name")
        index.description = request.POST.get("description")
        index.save()

        messages.success(request, "✔ تم تعديل الفهرس بنجاح.")
        return redirect("manage_human_indexes")

    return render(request, "dashboard/edit_index.html", {
        "index": index
    })

  


#---------------------------------------------
# حذف فهرس
#---------------------------------------------
@login_required
def delete_human_index(request, pk):
    from classifier_app.models import HumanIndexCategory
    from django.contrib import messages

    cat = HumanIndexCategory.objects.get(id=pk)
    cat.delete()
    messages.success(request, "تم حذف الفهرس بنجاح.")
    return redirect("manage_human_indexes")
#---------------------------------------------
# إنشاء فهرس
#---------------------------------------------
@login_required
def create_index(request, domain_id):
    from classifier_app.models import TrainingDomain, HumanIndex

    domain = TrainingDomain.objects.get(id=domain_id)

    if request.method == "POST":
        name = request.POST.get("name")
        description = request.POST.get("description")

        HumanIndex.objects.create(
            domain=domain,
            name=name,
            description=description
        )

        messages.success(request, "✔ تم إنشاء الفهرس بنجاح.")
        return redirect("manage_human_indexes")

    return render(request, "dashboard/create_index.html", {
        "domain": domain
    })

#---------------------------------------------
# دالة صفحة التدريب المركزية
#---------------------------------------------
@login_required
def manage_training_page(request):
    from classifier_app.models import TrainingDomain, HumanIndex, TrainingDocument
    from django.contrib import messages

    # جلب المجال الحالي (إن وجد)
    domain = TrainingDomain.objects.first()

    # إنشاء أو تعديل المجال
    if request.method == "POST" and "save_domain" in request.POST:
        title = request.POST.get("title")
        description = request.POST.get("description")

        if not title:
            messages.error(request, "يجب إدخال عنوان المجال.")
        else:
            if domain:
                domain.title = title
                domain.description = description
                domain.save()
                messages.success(request, "تم تعديل مجال التدريب بنجاح.")
            else:
                domain = TrainingDomain.objects.create(
                    title=title,
                    description=description,
                    created_by=request.user
                )
                messages.success(request, "تم إنشاء مجال التدريب بنجاح.")

    # إضافة فهرس جديد
    if request.method == "POST" and "add_index" in request.POST:
        if not domain:
            messages.error(request, "يجب إنشاء مجال تدريب أولًا.")
        else:
            name = request.POST.get("index_name")
            desc = request.POST.get("index_desc")
            if not name:
                messages.error(request, "يجب إدخال اسم الفهرس.")
            else:
                HumanIndex.objects.create(
                    domain=domain,
                    name=name,
                    description=desc,
                    created_by=request.user
                )
                messages.success(request, "تم إضافة الفهرس بنجاح.")

    # رفع وثيقة تدريب
    if request.method == "POST" and "upload_doc" in request.POST:
        if not domain:
            messages.error(request, "يجب إنشاء مجال تدريب أولًا.")
        else:
            index_id = request.POST.get("doc_index")
            file = request.FILES.get("doc_file")

            if not index_id or not file:
                messages.error(request, "يجب اختيار فهرس ورفع ملف.")
            else:
                index = HumanIndex.objects.get(id=index_id)
                file_path = f"training_docs/{file.name}"

                with open(file_path, "wb+") as dest:
                    for chunk in file.chunks():
                        dest.write(chunk)

                TrainingDocument.objects.create(
                    domain=domain,
                    index=index,
                    file_name=file.name,
                    file_path=file_path
                )

                messages.success(request, "تم رفع وثيقة التدريب بنجاح.")

    # جلب البيانات للعرض
    indexes = HumanIndex.objects.filter(domain=domain) if domain else []
    docs = TrainingDocument.objects.filter(domain=domain) if domain else []

    return render(request, "dashboard/manage_training_page.html", {
        "domain": domain,
        "indexes": indexes,
        "docs": docs,
    })


# دالة حذف الفهرس
@login_required
def delete_index(request, pk):
    from classifier_app.models import HumanIndex, Document

    index = HumanIndex.objects.get(pk=pk)
    doc_count = Document.objects.filter(index=index).count()

    if doc_count > 0:
        messages.error(request, "❌ لا يمكن حذف الفهرس لأنه يحتوي على وثائق.")
    else:
        index.delete()
        messages.success(request, "✔ تم حذف الفهرس بنجاح.")

    return redirect("manage_human_indexes")


# دالة تعديل الفهرس

# ---------------------------------------------------------
# صفحة إدارة المشاريع وتبديل المجال الفعّال
# ---------------------------------------------------------
@login_required
@permission_required("classifier_app.can_view_dashboard", raise_exception=True)
def manage_domains_view(request):
    from classifier_app.models import TrainingDomain, HumanIndex, Document

    domains = TrainingDomain.objects.all()

    # بناء بيانات إضافية لكل مشروع
    domain_info = []
    for d in domains:
        indexes = HumanIndex.objects.filter(domain=d)
        doc_count = Document.objects.filter(domain=d).count()

        domain_info.append({
            "domain": d,
            "indexes": indexes,
            "doc_count": doc_count,
        })

    return render(request, "dashboard/manage_domains.html", {
        "domain_info": domain_info
    })


    return render(request, "dashboard/manage_domains.html", {
        "domain_data": domain_data,
    })


# ---------------------------------------------------------
# تفعيل مشروع معين
# ---------------------------------------------------------
@login_required
@permission_required("classifier_app.change_trainingdomain", raise_exception=True)
def activate_domain_view(request, domain_id):
    from classifier_app.models import TrainingDomain
    from django.contrib import messages

    # إلغاء تفعيل جميع المشاريع
    TrainingDomain.objects.update(is_active=False)

    # تفعيل المشروع المطلوب فقط
    domain = TrainingDomain.objects.get(id=domain_id)
    domain.is_active = True

    # ⚠️ مهم جداً: لا نلمس is_trained هنا إطلاقاً
    # يبقى كما هو (False للمشاريع الجديدة، True للمشاريع المدرّبة)

    domain.save()

    messages.success(request, "✔ تم تفعيل المشروع بنجاح")
    return redirect("manage_domains")

# ---------------------------------------------------------
# صفحة إنشاء مشروع جديد
# ---------------------------------------------------------
@login_required
@permission_required("classifier_app.can_view_dashboard", raise_exception=True)
def create_domain_view(request):
    from classifier_app.models import TrainingDomain
    from django.contrib import messages
    from dashboard.views import clean_folder_name   # ← استدعاء الدالة الموجودة

    if request.method == "POST":
        title = request.POST.get("title")
        description = request.POST.get("description")

        if not title:
            messages.error(request, "يجب إدخال اسم المشروع.")
        else:
            # تنظيف اسم المشروع قبل التخزين
            clean_title = clean_folder_name(title)

            TrainingDomain.objects.create(
                title=clean_title,
                description=description,
            )

            messages.success(request, "✔ تم إنشاء المشروع الجديد بنجاح.")
            return redirect("manage_domains")

    return render(request, "dashboard/create_domain.html")


#-----------------------------------------
# دالة حذف المشروع
#-----------------------------------------
#---------------------------------------------
# حذف مشروع (TrainingDomain)
#---------------------------------------------
@login_required
def delete_domain(request, domain_id):
    from classifier_app.models import TrainingDomain, HumanIndex, Document
    from django.contrib import messages

    domain = TrainingDomain.objects.get(id=domain_id)

    # حذف الوثائق المرتبطة بالمشروع
    Document.objects.filter(domain=domain).delete()

    # حذف الفهارس المرتبطة بالمشروع
    HumanIndex.objects.filter(domain=domain).delete()

    # حذف المشروع نفسه
    domain.delete()

    messages.success(request, "✔ تم حذف المشروع بنجاح.")
    return redirect("manage_domains")

# دالة عرض الوثيقة
@login_required
def view_document(request, document_id):
    from classifier_app.models import Document

    document = Document.objects.get(id=document_id)

    return render(request, "dashboard/view_document.html", {
        "document": document
    })


def model_training_page(request):
    import os
    import pandas as pd
    from django.conf import settings

    # المسار الصحيح داخل media
    training_file = os.path.join(
        settings.MEDIA_ROOT,
        "training_exports",
        "manual_training_dataset.csv"
    )

    training_file_exists = os.path.exists(training_file)

    if training_file_exists:
        df = pd.read_csv(training_file)
        file_size = os.path.getsize(training_file)
        record_count = len(df)
    else:
        file_size = 0
        record_count = 0

    return render(request, "dashboard/model_training.html", {
        "training_file": training_file,
        "training_file_exists": training_file_exists,
        "file_size": file_size,
        "record_count": record_count,
    })

# إنشاء ملف التدريب الكامل
def generate_training_file_view(request):

    import numpy as np
    import pandas as pd

    from django.contrib import messages
    from django.shortcuts import redirect

    from classifier_app.models import (
        Document,
        TrainingDomain,
        HumanIndex,
    )

    from classifier_app.classifier_service import (
        build_features,
        save_document_representation,
    )

    from classifier_app.ml_paths import (
        get_domain_training_file,
    )

    # =========================================================
    # 1) الحصول على المشروع الفعّال
    # =========================================================

    active_domain = (
        TrainingDomain.objects
        .filter(is_active=True)
        .first()
    )

    if active_domain is None:

        messages.error(
            request,
            "لا يوجد مشروع مفعل."
        )

        return redirect(
            "model_training_page"
        )

    # =========================================================
    # 2) الحصول على فهارس المشروع
    # =========================================================

    indexes = (
        HumanIndex.objects
        .filter(domain=active_domain)
        .order_by("id")
    )

    if not indexes.exists():

        messages.error(
            request,
            "لا توجد فهارس ضمن هذا المشروع."
        )

        return redirect(
            "model_training_page"
        )

    # =========================================================
    # 3) وثائق المشروع التي لديها فهرس يدوي
    # =========================================================

    documents = (
        Document.objects
        .filter(
            domain=active_domain,
            index__isnull=False,
        )
        .select_related(
            "domain",
            "index"
        )
        .order_by("id")
    )

    if not documents.exists():

        messages.error(
            request,
            "لا توجد وثائق مفهرسة ضمن هذا المشروع."
        )

        return redirect(
            "model_training_page"
        )

    # =========================================================
    # 4) التحقق من الحد الأدنى المطلوب لكل فهرس
    # =========================================================

    missing_requirements = []

    for index in indexes:

        valid_count = (
            documents
            .filter(index=index)
            .exclude(ocr_text__isnull=True)
            .exclude(ocr_text="")
            .count()
        )

        if (
            index.min_required > 0
            and valid_count < index.min_required
        ):

            missing_requirements.append(
                f"{index.name}: "
                f"{valid_count}/{index.min_required}"
            )

    if missing_requirements:

        messages.error(
            request,
            (
                "لا يمكن إنشاء ملف التدريب. "
                "عدد الوثائق غير كافٍ لبعض الفهارس: "
                + " | ".join(missing_requirements)
            )
        )

        return redirect(
            "model_training_page"
        )

    # =========================================================
    # 5) تجهيز بيانات التدريب
    # =========================================================

    rows = []

    errors = []

    for doc in documents:



        # -----------------------------------------------------
        # نص OCR
        # -----------------------------------------------------

        text = (
            doc.ocr_text
            or ""
        ).strip()

        if not text:

            errors.append(
                f"Document {doc.id}: OCR text is empty."
            )

            continue

        try:

            # =================================================
            # 6) محاولة استخدام combined_embedding الموجود
            #    مسبقًا في قاعدة البيانات
            # =================================================

            features = None

            if doc.combined_embedding:

                try:

                    combined = np.asarray(
                        doc.combined_embedding,
                        dtype=np.float32
                    ).reshape(-1)

                    # يجب أن يكون:
                    # 768 CAMeLBERT
                    # +
                    # 128 Projection
                    # =
                    # 896
                    if combined.shape[0] != 896:

                        raise ValueError(
                            "Stored combined_embedding "
                            f"has {combined.shape[0]} values "
                            "instead of 896."
                        )

                    emb = combined[:768]

                    z = combined[768:]

                    if emb.shape[0] != 768:

                        raise ValueError(
                            "Invalid CAMeLBERT part."
                        )

                    if z.shape[0] != 128:

                        raise ValueError(
                            "Invalid Projection part."
                        )

                    features = {
                        "emb": emb,
                        "z": z,
                        "combined": combined,
                    }

                except Exception:

                    # إذا كانت القيمة القديمة معطوبة
                    # نعيد إنشاء التمثيل من OCR
                    features = None

            # =================================================
            # 7) وثيقة قديمة بدون representation
            #    أو representation غير صالح
            # =================================================

            if features is None:

                features = build_features(
                    text
                )

            emb = np.asarray(
                features["emb"],
                dtype=np.float32
            ).reshape(-1)

            z = np.asarray(
                features["z"],
                dtype=np.float32
            ).reshape(-1)

            combined = np.asarray(
                features["combined"],
                dtype=np.float32
            ).reshape(-1)

            # =================================================
            # 8) Validation نهائي
            # =================================================

            if emb.shape[0] != 768:

                raise ValueError(
                    f"Invalid embedding size: "
                    f"{emb.shape[0]}. Expected 768."
                )

            if z.shape[0] != 128:

                raise ValueError(
                    f"Invalid projection size: "
                    f"{z.shape[0]}. Expected 128."
                )

            if combined.shape[0] != 896:

                raise ValueError(
                    f"Invalid combined size: "
                    f"{combined.shape[0]}. Expected 896."
                )

            # =================================================
            # 9) حفظ representation
            #
            # يتم هنا:
            # - حفظ combined_embedding في DB
            # - إنشاء CSV مستقل للوثيقة
            #   داخل data/ocr_output/domain_...
            # =================================================


            save_document_representation(
                document=doc,
                features={
                    "emb": emb,
                    "z": z,
                    "combined": combined,
                },
                index=doc.index,
            )

            # =================================================
            # 10) إضافة الوثيقة إلى Dataset العام
            # =================================================

            rows.append({

                "document_id":
                    doc.id,

                "domain_id":
                    active_domain.id,

                "domain_title":
                    active_domain.title,

                "record_number":
                    doc.record_number or "",

                "doc_type":
                    doc.doc_type or "",

                "index_id":
                    doc.index.id,

                # الفئة الصحيحة التي سيتعلم عليها
                # LogisticRegression
                "corrected_label":
                    doc.index.name,

                "text":
                    text,

                # CAMeLBERT = 768
                "emb":
                    emb.tolist(),

                # ProjectionHead = 128
                "z":
                    z.tolist(),

                # final representation = 896
                "combined":
                    combined.tolist(),
            })

        except Exception as exc:

            errors.append(
                f"Document {doc.id}: {str(exc)}"
            )

    # =========================================================
    # 11) التأكد أن لدينا بيانات صالحة
    # =========================================================

    if not rows:

        messages.error(
            request,
            (
                "لم يتم إنشاء ملف التدريب، "
                "لأنه لا توجد وثائق صالحة."
            )
        )

        return redirect(
            "model_training_page"
        )

    # =========================================================
    # 12) DataFrame
    # =========================================================

    df = pd.DataFrame(
        rows
    )

    # =========================================================
    # 13) التحقق من وجود فئتين على الأقل
    # =========================================================

    unique_labels = (
        df["corrected_label"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    if len(unique_labels) < 2:

        messages.error(
            request,
            (
                "لا يمكن إنشاء ملف تدريب صالح، "
                "لأن البيانات تحتوي على فئة واحدة فقط."
            )
        )

        return redirect(
            "model_training_page"
        )

    # =========================================================
    # 14) التأكد مرة أخيرة من جميع combined vectors
    # =========================================================

    for row_number, combined_value in enumerate(
        df["combined"],
        start=1
    ):

        arr = np.asarray(
            combined_value,
            dtype=np.float32
        ).reshape(-1)

        if arr.shape[0] != 896:

            messages.error(
                request,
                (
                    f"خطأ في السجل رقم {row_number}: "
                    f"التمثيل يحتوي {arr.shape[0]} "
                    "قيمة بدل 896."
                )
            )

            return redirect(
                "model_training_page"
            )

    # =========================================================
    # 15) مسار Dataset الخاص بهذا Domain
    # =========================================================

    output_path = (
        get_domain_training_file(
            active_domain
        )
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    # =========================================================
    # 16) حفظ ملف التدريب
    # =========================================================

    df.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig"
    )


    # =========================================================
    # 17) Dataset جديد يعني أن النموذج الحالي
    #     يحتاج إلى إعادة تدريب
    # =========================================================

    active_domain.is_trained = False

    active_domain.save(
        update_fields=[
            "is_trained"
        ]
    )

    # =========================================================
    # 18) رسالة النتيجة
    # =========================================================

    success_message = (
        "✔️ تم إنشاء ملف التدريب بنجاح. "
        f"عدد السجلات: {len(df)} | "
        f"عدد الفئات: {len(unique_labels)}"
    )

    if errors:

        success_message += (
            f" | تم تجاهل {len(errors)} "
            "وثيقة بسبب أخطاء."
        )

    messages.success(
        request,
        success_message
    )

    return redirect(
        "model_training_page"
    )











from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from classifier_app.models import Document, HumanIndex

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from classifier_app.models import Document, HumanIndex

@login_required
@permission_required("classifier_app.view_document", raise_exception=True)
def document_detail_view(request, document_id):
    document = get_object_or_404(Document, id=document_id)
    indexes = HumanIndex.objects.filter(domain=document.domain)

    return render(request, "dashboard/document_detail.html", {
        "document": document,
        "indexes": indexes,
        "active_domain": document.domain,
    })




from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from classifier_app.models import Document, HumanIndex

def accept_classification(request, document_id):
    document = get_object_or_404(Document, id=document_id)
    # ببساطة نعتبر أن التصنيف الحالي صحيح
    messages.success(request, "✔ تم قبول التصنيف الحالي للوثيقة.")
    return redirect("document_detail", document_id=document.id)

def correct_classification(request, document_id):
    document = get_object_or_404(Document, id=document_id)
    if request.method == "POST":
        index_id = request.POST.get("correct_index")
        if index_id:
            new_index = get_object_or_404(HumanIndex, id=index_id)
            old_index = document.index
            document.index = new_index
            document.save()
            messages.success(
                request,
                f"✏️ تم تصحيح الفهرس من {old_index} إلى {new_index}."
            )
    return redirect("document_detail", document_id=document.id)

from django.db.models import Q

@login_required
@permission_required("classifier_app.view_document", raise_exception=True)
def documents_list_view(request):
    active_domain = TrainingDomain.objects.filter(is_active=True).first()
    query = request.GET.get("q", "")
    documents = Document.objects.filter(domain=active_domain)

    if query:
        documents = documents.filter(
            Q(record_number__icontains=query) |
            Q(doc_type__icontains=query) |
            Q(file_path__icontains=query) |
            Q(index__name__icontains=query) |
            Q(classification_status__icontains=query)
        )

    documents = documents.order_by("-uploaded_at")

    return render(request, "dashboard/documents_list.html", {
        "documents": documents,
        "query": query,
        "active_domain": active_domain,
    })

@login_required
def documents_list_view(request):
    from classifier_app.models import Document

    q = request.GET.get("q", "")
    if q:
        docs = Document.objects.filter(record_number__icontains=q).order_by("-uploaded_at")
    else:
        docs = Document.objects.all().order_by("-uploaded_at")

    return render(request, "dashboard/documents_list.html", {
        "documents": docs,
        "query": q,
    })
import os
from django.conf import settings

def save_ocr_text_file(document):
    """
    تخزين نص الوثيقة الناتج عن OCR داخل project_root/data/ocr_output/
    ضمن مجلد المجال، ثم مجلد رقم السجل، وباسم مركب.
    """

    if not document.ocr_text:
        return None

    # المسار الأساسي
    base_dir = os.path.join(settings.BASE_DIR, "project_root", "data", "ocr_output")

    # مجلد المجال
    domain_folder = os.path.join(base_dir, document.domain.title)

    # مجلد رقم السجل
    record_folder = os.path.join(domain_folder, str(document.record_number))

    # إنشاء المجلدات إذا لم تكن موجودة
    os.makedirs(record_folder, exist_ok=True)

    # اسم الفهرس
    index_name = document.index.name if document.index else "بدون_فهرس"

    # اسم الملف الأصلي
    original_name = os.path.splitext(document.file_name)[0]

    # الاسم المركب للملف النصي
    filename = f"{document.record_number}_{index_name}_{original_name}.txt"

    file_path = os.path.join(record_folder, filename)

    # كتابة النص داخل الملف
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(document.ocr_text)

    return file_path
import os
import re
import unicodedata
from django.conf import settings
from django.contrib import messages
from classifier_app.models import TrainingDomain, HumanIndex, Document
from classifier_app.classifier_service import (
    classify_document,
    build_features,
    save_document_representation,
)
from ocr_module.ocr_engine import run_ocr_on_image

# ================================
# دالة تنظيف أسماء المجلدات
# ================================
def clean_folder_name(name):
    if not name:
        return "folder"

    # إزالة المسافات في البداية والنهاية
    name = name.strip()

    # توحيد الترميز
    name = unicodedata.normalize("NFKD", name)

    # استبدال المسافات بـ _
    name = re.sub(r"\s+", "_", name)

    # إزالة الرموز غير الصالحة
    name = re.sub(r"[^\w\-ا-ي]", "", name)

    if not name:
        name = "folder"

    return name


@login_required
@permission_required("classifier_app.add_document", raise_exception=True)
def upload_document_view(request):
    from classifier_app.models import TrainingDomain, HumanIndex, Document
    from classifier_app.classifier_service import classify_document
    from ocr_module.ocr_engine import run_ocr_on_image
    from django.contrib import messages
    from django.conf import settings
    import os
    from classifier_app.classifier_service import (
        build_features,
        save_document_representation,
    )

    # الحصول على المشروع المفعل
    active_domain = TrainingDomain.objects.filter(is_active=True).first()
    if not active_domain:
        messages.error(request, "لا يوجد مشروع مفعل.")
        return redirect("dashboard")

    indexes = HumanIndex.objects.filter(domain=active_domain)
    is_trained = active_domain.is_trained

    if request.method == "POST":
        record_number = request.POST.get("record_number")
        doc_type = request.POST.get("doc_type")
        file = request.FILES.get("file")
        index_id = request.POST.get("index")

        if not file:
            messages.error(request, "لم يتم رفع أي ملف.")
            return redirect("upload_document")

        # تنظيف أسماء المجلدات للمسار الأساسي
        domain_title = clean_folder_name(active_domain.title)
        record_number_clean = clean_folder_name(record_number)

        # مسار حفظ الملف (استخدام الأسماء المنظّفة للمشروع والسجل فقط)
        project_folder = os.path.join(settings.MEDIA_ROOT, domain_title)
        os.makedirs(project_folder, exist_ok=True)

        record_folder = os.path.join(project_folder, record_number_clean)
        os.makedirs(record_folder, exist_ok=True)

        # في البداية نضع الملف داخل مجلد السجل مباشرة
        final_file_path = os.path.join(record_folder, file.name)

        # حفظ الملف فعليًا
        with open(final_file_path, "wb+") as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        # تشغيل OCR
        ocr_text = run_ocr_on_image(final_file_path)

        # إنشاء الوثيقة
        document = Document.objects.create(
            domain=active_domain,
            record_number=record_number,
            doc_type=doc_type,
            file_name=file.name,
            file_path=final_file_path,
            ocr_text=ocr_text,
            index=None
        )

        # حفظ نص OCR داخل قاعدة البيانات
        document.ocr_text = ocr_text
        document.ocr_status = "done"
        document.save(update_fields=["ocr_text", "ocr_status"])

        # تخزين النص في ملف خارجي
        save_ocr_text_file(document)

        # =====================================================
        # إنشاء التمثيل العددي وحفظه في DB + CSV (إذا كان هناك فهرس)
        # =====================================================
        if document.index is not None:
            features = build_features(document.ocr_text)
            save_document_representation(
                document=document,
                features=features,
                index=document.index
            )

        # =========================================================
        # إذا المشروع مدرب → Auto Classification
        # =========================================================
        if is_trained:
            result = classify_document(document, move_file=True)

            if result["success"]:
                confidence = result.get("confidence")
                confidence_text = (
                    f"{confidence * 100:.2f}%" if confidence else "غير متوفر"
                )

                # حفظ الفهرس المقترح
                predicted_index = HumanIndex.objects.filter(
                    id=result["index_id"]
                ).first()

                document.index = predicted_index
                document.classification_result = result["label"]
                document.save(update_fields=["index", "classification_result"])

                messages.success(
                    request,
                    (
                        "تم رفع الوثيقة وتصنيفها تلقائيًا: "
                        f"{result['label']} — الثقة: {confidence_text}"
                    )
                )
            else:
                messages.error(
                    request,
                    (
                        "تم رفع الوثيقة ولكن فشل التصنيف التلقائي: "
                        f"{result.get('error')}"
                    )
                )

            # في كل الأحوال بعد مشروع مدرّب → نذهب لتقرير التصنيف
            return redirect("classification_report", document_id=document.id)

        # =========================================================
        # إذا المشروع غير مدرب → Manual HumanIndex
        # =========================================================
        else:
            if index_id:
                manual_index = HumanIndex.objects.filter(id=index_id).first()
                document.index = manual_index
                document.save(update_fields=["index"])

                messages.success(
                    request,
                    "تم رفع الوثيقة بنجاح وتخزينها في المسار الصحيح."
                )

                # يمكن لاحقًا استخدام build_features + حفظ التمثيل العددي هنا إن أردتِ
                return redirect("classification_report", document_id=document.id)
            else:
                messages.error(
                    request,
                    "المشروع غير مدرّب؛ يجب اختيار الفهرس يدويًا."
                )
                return redirect("upload_document")

    return render(request, "dashboard/upload_document.html", {
        "active_domain": active_domain,
        "indexes": indexes,
        "is_trained": is_trained,
    })


@login_required
def correct_document_view(request, document_id):
    from classifier_app.models import Document, HumanIndex

    doc = Document.objects.get(id=document_id)
    new_index_id = request.GET.get("index")

    if new_index_id:
        new_index = HumanIndex.objects.get(id=new_index_id)
        doc.index = new_index
        doc.classification_result = new_index.name
        doc.classification_status = "done"
        doc.save()

    return redirect("document_detail", document_id=document_id)

@login_required
def rerun_ocr_view(request, document_id):
    from classifier_app.models import Document
    from ocr_module.ocr_engine import run_ocr_on_image

    doc = Document.objects.get(id=document_id)

    # إعادة تشغيل OCR على الملف الموجود
    with open(doc.file_path, "rb") as f:
        ocr_text = run_ocr_on_image(f)

    doc.ocr_text = ocr_text
    doc.ocr_status = "done"
    doc.save()
    document.ocr_text = new_text
    document.save()

    save_ocr_text_file(document)

    return redirect("document_detail", document_id=document_id)

@login_required
def accept_classification_view(request, document_id):
    from classifier_app.models import Document

    doc = Document.objects.get(id=document_id)
    doc.classification_status = "done"
    doc.save()

    return redirect("document_detail", document_id=document_id)



#----------------------------------
# عرض قائمة الأضابير (المشروع الفعّال فقط)
#----------------------------------
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from classifier_app.models import Document, TrainingDomain

@login_required
def archive_view(request):
    # الحصول على المشروع الفعّال
    active_domain = TrainingDomain.objects.filter(is_active=True).first()

    if not active_domain:
        messages.error(request, "لا يوجد مشروع مفعل.")
        return redirect("dashboard")

    # جلب الأضابير الخاصة بالمشروع الفعّال فقط
    raw_dossiers = (
        Document.objects
        .filter(domain=active_domain)
        .values("record_number")
        .distinct()
    )

    dossiers = []
    for d in raw_dossiers:
        rn = d["record_number"]

        # عدد الوثائق داخل نفس المشروع فقط
        count = Document.objects.filter(
            domain=active_domain,
            record_number=rn
        ).count()

        dossiers.append({
            "record_number": rn,
            "count": count,
        })

    return render(request, "dashboard/archive.html", {
        "dossiers": dossiers,
        "active_domain": active_domain,
    })





#----------------------------------
# عرض الوثائق داخل إضبارة
#----------------------------------
@login_required
def dossier_detail_view(request, record_number):
    active_domain = TrainingDomain.objects.filter(is_active=True).first()

    if not active_domain:
        messages.error(request, "لا يوجد مشروع مفعل.")
        return redirect("dashboard")

    # مسار السجل الفعلي
    domain_folder = clean_folder_name(active_domain.title)
    record_folder = os.path.join(
        settings.MEDIA_ROOT,
        domain_folder,
        clean_folder_name(record_number)
    )

    documents = []

    # إذا كان مجلد السجل موجودًا فعليًا
    if os.path.exists(record_folder):

        # قراءة الفهارس الموجودة فعليًا داخل المجلد
        for index_name in os.listdir(record_folder):
            index_path = os.path.join(record_folder, index_name)

            if os.path.isdir(index_path):

                # قراءة الملفات داخل الفهرس
                for file_name in os.listdir(index_path):
                    file_path = os.path.join(index_path, file_name)

                    # مطابقة الملف مع الوثيقة في قاعدة البيانات
                    doc = Document.objects.filter(
                        domain=active_domain,
                        record_number=record_number,
                        file_name=file_name
                    ).first()

                    if doc:
                        # وثيقة صالحة
                        documents.append(doc)
                    else:
                        # وثيقة غير صالحة (لها ملف لكن لا يوجد سجل في قاعدة البيانات)
                        documents.append({
                            "file_name": file_name,
                            "index_name": index_name,
                            "invalid": True
                        })

    return render(request, "dashboard/dossier_detail.html", {
        "record_number": record_number,
        "documents": documents,
        "active_domain": active_domain,
    })







