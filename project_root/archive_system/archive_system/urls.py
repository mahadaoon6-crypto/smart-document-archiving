from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

# استيراد دوال تسجيل الدخول والخروج
from dashboard.views import login_view, logout_view

urlpatterns = [
    path('admin/', admin.site.urls),

    # روابط تطبيق لوحة التحكم
    path('dashboard/', include('dashboard.urls')),

    # تسجيل الدخول والخروج
    path('login/', login_view, name="login"),
    path('logout/', logout_view, name="logout"),

    # إعادة توجيه الصفحة الرئيسية إلى صفحة تسجيل الدخول
    path('', lambda request: redirect('login')),
]






