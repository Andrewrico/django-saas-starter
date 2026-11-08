"""Root URL configuration."""

from allauth.account.decorators import secure_admin_login
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.accounts.mfa import EnrollTOTPView, VerifiedEmailView
from apps.blog.sitemaps import PostSitemap, StaticViewSitemap
from apps.blog.views import robots_txt
from apps.core.dashboard import staff_dashboard
from apps.core.job_trigger import run_jobs
from apps.core.views import healthz

admin.site.login = secure_admin_login(admin.site.login)
# Link the analytics dashboard from the default admin index.
admin.site.index_template = "admin/dashboard_index.html"

sitemaps = {
    "static": StaticViewSitemap,
    "posts": PostSitemap,
}

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("internal/jobs/run/", run_jobs, name="run-jobs"),
    path("admin/dashboard/", staff_dashboard, name="admin-dashboard"),
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("api/auth/", include("apps.accounts.api_urls")),
    path("api/billing/", include("apps.billing.urls")),
    path("api/projects/", include("apps.example.urls")),
    path("ai/", include("apps.ai.urls")),
    path("accounts/email/", VerifiedEmailView.as_view()),
    path("accounts/2fa/totp/activate/", EnrollTOTPView.as_view()),
    path("accounts/", include("allauth.urls")),
    path("blog/", include("apps.blog.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("robots.txt", robots_txt, name="robots"),
    path("", include("apps.accounts.urls")),
]
