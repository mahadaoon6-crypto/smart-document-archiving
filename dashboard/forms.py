from django import forms

class DocumentUploadForm(forms.Form):
    well_id = forms.CharField(label="رقم البئر", max_length=50)
    dossier_type = forms.CharField(label="نوع الوثيقة", max_length=50)
    file = forms.FileField(label="الوثيقة")