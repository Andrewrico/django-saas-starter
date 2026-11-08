import pytest
from django.utils import timezone

from apps.blog.markdown import render_markdown
from apps.blog.models import Post
from apps.blog.views import POSTS_PER_PAGE

from .conftest import PASSWORD

pytestmark = pytest.mark.django_db


def make_post(**kwargs) -> Post:
    defaults = {
        "title": "Hello",
        "slug": "hello",
        "summary": "A short summary",
        "body": "Hello **world**",
        "status": Post.Status.PUBLISHED,
        "published_at": timezone.now(),
    }
    defaults.update(kwargs)
    return Post.objects.create(**defaults)


def test_list_shows_published_only(client):
    make_post(slug="pub", title="Published")
    make_post(slug="draft", title="Secret", status=Post.Status.DRAFT, published_at=None)
    resp = client.get("/blog/")
    assert resp.status_code == 200
    assert b"Published" in resp.content
    assert b"Secret" not in resp.content
    assert b">Blog<" in resp.content  # nav link present via base


def test_nav_includes_blog_on_home(client):
    resp = client.get("/")
    assert b'href="/blog/"' in resp.content


def test_detail_404_for_draft_unless_staff(client, make_user):
    make_post(slug="drafty", status=Post.Status.DRAFT, published_at=None)
    assert client.get("/blog/drafty/").status_code == 404
    staff = make_user(email="editor@example.com", is_staff=True)
    client.force_login(staff)
    resp = client.get("/blog/drafty/")
    assert resp.status_code == 200
    assert b"Draft" in resp.content


def test_detail_renders_markdown(client):
    make_post(body="## Heading\n\nA [link](https://example.com/path).")
    resp = client.get("/blog/hello/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "<h2>Heading</h2>" in body
    assert 'rel="noopener nofollow"' in body
    assert "https://example.com/path" in body


@pytest.mark.parametrize(
    "payload",
    [
        '<script>alert("x")</script>',
        '<img src=x onerror="alert(1)">',
        '<a href="javascript:alert(1)">click</a>',
        '<p onclick="alert(1)">hi</p>',
    ],
)
def test_markdown_sanitises_xss(payload):
    html = render_markdown(payload)
    assert "<script" not in html.lower()
    assert "javascript:" not in html.lower()
    assert "onerror" not in html.lower()
    assert "onclick" not in html.lower()


def test_feed_lists_published(client):
    make_post(title="Feed me")
    make_post(slug="nope", title="Nope", status=Post.Status.DRAFT, published_at=None)
    resp = client.get("/blog/feed/")
    assert resp.status_code == 200
    assert b"Feed me" in resp.content
    assert b"Nope" not in resp.content


def test_sitemap_and_robots(client):
    make_post(slug="mapped", title="Mapped")
    make_post(slug="hidden", status=Post.Status.DRAFT, published_at=None)
    sm = client.get("/sitemap.xml")
    assert sm.status_code == 200
    text = sm.content.decode()
    assert "/blog/mapped/" in text
    assert "/blog/hidden/" not in text
    assert 'loc="' in text or "<loc>" in text
    robots = client.get("/robots.txt")
    assert robots.status_code == 200
    assert b"Sitemap:" in robots.content
    assert b"sitemap.xml" in robots.content


def test_pagination(client):
    for i in range(POSTS_PER_PAGE + 2):
        make_post(slug=f"p-{i}", title=f"Post {i}", published_at=timezone.now())
    page1 = client.get("/blog/")
    assert page1.status_code == 200
    assert b"?page=2" in page1.content or b"page=2" in page1.content
    page2 = client.get("/blog/?page=2")
    assert page2.status_code == 200


def test_admin_post_changelist(client, make_user):
    admin = make_user(email="root@example.com", is_staff=True, is_superuser=True)
    admin.set_password(PASSWORD)
    admin.save()
    client.force_login(admin)
    assert client.get("/admin/blog/post/").status_code == 200


def test_publish_sets_published_at():
    post = Post(title="T", slug="t", body="x", status=Post.Status.PUBLISHED)
    post.save()
    assert post.published_at is not None
    assert post.is_published
    assert str(post) == "T"
    assert "world" in make_post(slug="sum", summary="", body="Hello world").plain_summary()
