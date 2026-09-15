from django.contrib.auth.models import User, Group
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render

@login_required
@permission_required("classifier_app.can_view_dashboard", raise_exception=True)
def user_management_view(request):
    users = User.objects.all().order_by('username')
    groups = Group.objects.all().order_by('name')

    return render(request, "dashboard/user_management.html", {
        "users": users,
        "groups": groups,
    })
