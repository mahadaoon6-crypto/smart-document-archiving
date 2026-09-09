from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from classifier_app.models import Well, Document, DocumentTimeline, ManualIndex
from .forms import DocumentUploadForm
import os

from django.contrib.auth.decorators import login_required, permission_required
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout

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
from classifier_app.classifier import classify_document
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
    active_domain = TrainingDomain.objects.filter(is_active=True).first()
    if not active_domain:
        messages.error(request, "لا يوجد مشروع مفعل للتصنيف.")
        return redirect("document_detail", document_id=document.id)

    # الحصول على الفهارس
    indexes = HumanIndex.objects.filter(domain=active_domain)
    index_names = [idx.name for idx in indexes]

    # تشغيل النموذج
    result, probabilities, emb, z, combined = classify_document(text)

    # التأكد أن النتيجة ضمن الفهارس
    if result not in index_names:
        result = "فهرس غير معروف ضمن المجال الفعّال"

    # حفظ النتيجة
    document.classification_result = result
    document.classification_status = "done"
    document.save()

    # حفظ ملف .class.txt
    class_file = document.file_path + ".class.txt"
    with open(class_file, "w", encoding="utf-8") as f:
        f.write(result)

    # سجل زمني
    DocumentTimeline.objects.create(
        document=document,
        action=f"إعادة تشغيل التصنيف — النتيجة الجديدة: {result}"
    )

    messages.success(request, f"✔️ تم إعادة التصنيف — النتيجة الجديدة: {result}")
    return redirect("document_detail", document_id=document.id)

from django.shortcuts import render, redirect
from django.contrib import messages
from classifier_app.models import Document, TrainingDomain, HumanIndex
from classifier_app.classifier import classify_document

@login_required
@permission_required("classifier_app.view_document", raise_exception=True)
def classification_report_view(request, document_id):
    document = Document.objects.get(id=document_id)
    text = document.ocr_text or ""

    if not text.strip():
        result = "no_text"
        probabilities = {}
        emb, z, combined = [], [], []
    else:
        # الحصول على المجال الفعّال
        active_domain = TrainingDomain.objects.filter(is_active=True).first()
        if not active_domain:
            messages.error(request, "لا يوجد مشروع مفعل للتصنيف.")
            return redirect("document_detail", document_id=document.id)

        # الحصول على الفهارس
        indexes = HumanIndex.objects.filter(domain=active_domain)
        index_names = [idx.name for idx in indexes]

        # تشغيل النموذج
        result, probabilities, emb, z, combined = classify_document(text)

        # التأكد أن النتيجة ضمن الفهارس
        if result not in index_names:
            result = "فهرس غير معروف ضمن المجال الفعّال"

    context = {
        "document": document,
        "result": result,
        "probabilities": probabilities,
        "text": text,
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

    if request.method == "POST":
        title = request.POST.get("title")
        description = request.POST.get("description")

        if not title:
            messages.error(request, "يجب إدخال اسم المشروع.")
        else:
            TrainingDomain.objects.create(
                title=title,
                description=description,
              #  created_by=request.user
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
    from classifier_app.models import Document, TrainingDomain
    import pandas as pd
    import numpy as np
    import torch
    from transformers import AutoTokenizer, AutoModel
    from classifier_app.text_cleaning import clean_text
    from classifier_app.classifier import ProjectionHead
    from django.contrib import messages
    import os
    from django.conf import settings

    # الحصول على المشروع الفعّال
    active_domain = TrainingDomain.objects.filter(is_active=True).first()
    if not active_domain:
        messages.error(request, "لا يوجد مشروع مفعل.")
        return redirect("model_training_page")

    # تحميل CAMeLBERT
    MODEL_NAME = "CAMeL-Lab/bert-base-arabic-camelbert-msa"
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    bert_model = AutoModel.from_pretrained(MODEL_NAME)
    bert_model.eval()

    # تحميل Projection Head
    projection_path = os.path.join(
        settings.BASE_DIR.parent,
        "data",
        "self_supervised_projection.pt"
    )

    projection_model = ProjectionHead()
    projection_model.load_state_dict(
        torch.load(projection_path, map_location="cpu")
    )
    projection_model.eval()

    def get_embedding(text):
        cleaned = clean_text(text)
        inputs = tokenizer(
            cleaned,
            return_tensors="pt",
            truncation=True,
            max_length=512
        )
        with torch.no_grad():
            outputs = bert_model(**inputs)
        emb = outputs.last_hidden_state[:, 0, :].squeeze().numpy()
        return emb.astype("float32")

    rows = []

    # ⭐ الوثائق الخاصة بالمشروع الفعّال فقط
    documents = Document.objects.filter(domain=active_domain)

    for doc in documents:

        if doc.index is None:
            continue

        text = doc.ocr_text or ""
        if not text.strip():
            continue

        emb = get_embedding(text)

        emb_tensor = torch.tensor(emb).unsqueeze(0)
        with torch.no_grad():
            z = projection_model(emb_tensor).squeeze().numpy()

        combined = np.concatenate([emb, z])

        rows.append({
            "document_id": doc.id,
            "record_number": doc.record_number,
            "doc_type": doc.doc_type,
            "corrected_label": doc.index.name,
            "text": text,
            "emb": emb.tolist(),
            "z": z.tolist(),
            "combined": combined.tolist()
        })

    df = pd.DataFrame(rows)

    output_path = os.path.join(
        settings.MEDIA_ROOT,
        "training_exports",
        "manual_training_dataset.csv"
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")

    messages.success(request, "✔ تم إنشاء ملف التدريب بنجاح!")
    return redirect("model_training_page")

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

@login_required
@permission_required("classifier_app.add_document", raise_exception=True)
def upload_document_view(request):
    from classifier_app.models import TrainingDomain, HumanIndex, Document, DocumentTimeline
    from classifier_app.classifier import classify_document
    from ocr_module.ocr_engine import run_ocr_on_image
    from django.contrib import messages
    from django.conf import settings
    import os

    # الحصول على المشروع المفعل
    active_domain = TrainingDomain.objects.filter(is_active=True).first()
    if not active_domain:
        messages.error(request, "لا يوجد مشروع مفعل للأرشفة.")
        return redirect("dashboard")

    print("DEBUG is_trained from DB:", active_domain.is_trained)

    indexes = HumanIndex.objects.filter(domain=active_domain)
    is_trained = active_domain.is_trained
    suggested_index = None

    if request.method == "POST":
        record_number = request.POST.get("record_number")
        doc_type = request.POST.get("doc_type")
        file = request.FILES.get("file")
        index_id = request.POST.get("index")

        project_folder = os.path.join(settings.MEDIA_ROOT, active_domain.title)
        os.makedirs(project_folder, exist_ok=True)

        record_folder = os.path.join(project_folder, record_number)
        os.makedirs(record_folder, exist_ok=True)

        ocr_text = run_ocr_on_image(file)

        if is_trained:
            try:
                suggested_index = classify_document(ocr_text, active_domain)
            except Exception:
                suggested_index = None

        final_index = None

        if index_id:
            final_index = HumanIndex.objects.filter(id=index_id).first()
        elif is_trained and suggested_index:
            final_index = suggested_index

        if final_index:
            index_folder = os.path.join(record_folder, final_index.name)
        else:
            index_folder = os.path.join(record_folder, "غير_مصنف")

        os.makedirs(index_folder, exist_ok=True)

        final_file_path = os.path.join(index_folder, file.name)
        with open(final_file_path, "wb+") as destination:
            for chunk in file.chunks():
                destination.write(chunk)

        doc = Document.objects.create(
            domain=active_domain,
            record_number=record_number,
            doc_type=doc_type,
            file_name=file.name,
            file_path=final_file_path,
            ocr_text=ocr_text,
            index=final_index,
            ocr_status="done",
            classification_result=final_index.name if final_index else None,
            classification_status="done" if final_index else "pending",
        )

        DocumentTimeline.objects.create(
            document=doc,
            action="تم رفع الوثيقة وتشغيل OCR والتصنيف"
        )

        messages.success(request, "✔ تم رفع الوثيقة بنجاح!")
        return redirect("document_detail", document_id=doc.id)

    index_stats = []
    show_training_ready_message = False

    if not is_trained:
        for idx in indexes:
            count = Document.objects.filter(index=idx).count()
            index_stats.append({
                "name": idx.name,
                "count": count,
                "min_required": idx.min_required,
                "ready": count >= idx.min_required
            })

        show_training_ready_message = all(item["ready"] for item in index_stats)

    return render(request, "dashboard/upload_document.html", {
        "active_domain": active_domain,
        "indexes": indexes,
        "is_trained": is_trained,
        "suggested_index": suggested_index,
        "index_stats": index_stats,
        "show_training_ready_message": show_training_ready_message
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

    return redirect("document_detail", document_id=document_id)

@login_required
def accept_classification_view(request, document_id):
    from classifier_app.models import Document

    doc = Document.objects.get(id=document_id)
    doc.classification_status = "done"
    doc.save()

    return redirect("document_detail", document_id=document_id)


def upload_document_view(request):
    from classifier_app.models import Document, HumanIndex
    from classifier_app.classifier import classify_text
    from ocr_module.ocr_engine import run_ocr_on_image
    import os

    if request.method == "POST":
        file = request.FILES.get("file")
        record_number = request.POST.get("record_number")
        doc_type = request.POST.get("doc_type")

        # إذا لم يصل الملف → لا شيء سيعمل
        if not file:
            messages.error(request, "لم يتم رفع أي ملف.")
            return redirect("upload_document")

        # حفظ الملف
        project_folder = os.path.join(settings.MEDIA_ROOT, "الديوان")
        record_folder = os.path.join(project_folder, record_number)
        os.makedirs(record_folder, exist_ok=True)

        file_path = os.path.join(record_folder, file.name)
        with open(file_path, "wb+") as dest:
            for chunk in file.chunks():
                dest.write(chunk)

        # تشغيل OCR
        ocr_text = run_ocr_on_image(file_path)

        # تشغيل التصنيف
        suggested_index_name = classify_text(ocr_text)
        suggested_index = HumanIndex.objects.filter(name=suggested_index_name).first()

        # إنشاء الوثيقة
        doc = Document.objects.create(
            record_number=record_number,
            doc_type=doc_type,
            file_path=file_path,
            ocr_text=ocr_text,
            classification_result=suggested_index_name,
            index=suggested_index,
            ocr_status="done",
            classification_status="done" if suggested_index else "pending",
        )

        return redirect("document_detail", document_id=doc.id)

    # GET
    indexes = HumanIndex.objects.all()
    return render(request, "dashboard/upload_document.html", {"indexes": indexes})
