from django.shortcuts import render

def classify_view(request):
    return render(request, "classifier_app/classify.html")
