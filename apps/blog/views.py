from __future__ import annotations

from django.core.paginator import Paginator
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from .models import Post

POSTS_PER_PAGE = 10


@require_GET
def post_list(request: HttpRequest) -> HttpResponse:
    qs = Post.objects.filter(status=Post.Status.PUBLISHED).select_related("author")
    page = Paginator(qs, POSTS_PER_PAGE).get_page(request.GET.get("page"))
    return render(request, "blog/post_list.html", {"page": page, "posts": page.object_list})


@require_GET
def post_detail(request: HttpRequest, slug: str) -> HttpResponse:
    post = get_object_or_404(Post.objects.select_related("author"), slug=slug)
    if post.status != Post.Status.PUBLISHED and not (request.user.is_authenticated and request.user.is_staff):
        raise Http404()
    return render(
        request,
        "blog/post_detail.html",
        {"post": post, "is_draft": post.status == Post.Status.DRAFT},
    )


@require_GET
def robots_txt(request: HttpRequest) -> HttpResponse:
    sitemap_url = request.build_absolute_uri("/sitemap.xml")
    body = f"User-agent: *\nAllow: /\nSitemap: {sitemap_url}\n"
    return HttpResponse(body, content_type="text/plain")
