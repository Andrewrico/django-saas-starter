from django.urls import path

from .feeds import LatestPostsFeed
from .views import post_detail, post_list

urlpatterns = [
    path("", post_list, name="blog-list"),
    path("feed/", LatestPostsFeed(), name="blog-feed"),
    path("<slug:slug>/", post_detail, name="blog-detail"),
]
