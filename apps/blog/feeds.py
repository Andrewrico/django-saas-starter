from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Atom1Feed

from .models import Post


class LatestPostsFeed(Feed):
    title = "Blog"
    link = "/blog/"
    description = "Latest published posts."
    feed_type = Atom1Feed

    def items(self):
        return Post.objects.filter(status=Post.Status.PUBLISHED).order_by("-published_at")[:20]

    def item_title(self, item: Post) -> str:
        return item.title

    def item_description(self, item: Post) -> str:
        return item.summary or item.plain_summary()

    def item_pubdate(self, item: Post):
        return item.published_at

    def item_updateddate(self, item: Post):
        return item.updated_at
