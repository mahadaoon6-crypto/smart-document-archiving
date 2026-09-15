from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render

@login_required
@permission_required("classifier_app.can_view_dashboard", raise_exception=True)
def user_permissions_view(request):
    user = request.user
    permissions = user.get_all_permissions()
    groups = user.groups.all()

    context = {
        "user": user,
        "permissions": permissions,
        "groups": groups,
    }
    return render(request, "dashboard/user_permissions.html", context)
