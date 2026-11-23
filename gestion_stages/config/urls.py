from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from accounts.views import RoleLoginView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("compte/login/", RoleLoginView.as_view(), name="login"),
    path("compte/", include("django.contrib.auth.urls")),   # login, logout, reset mot de passe (B1.3)
    path("", include("accounts.urls")),
    path("", include("stages.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
