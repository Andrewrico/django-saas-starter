# Blog

Markdown blog in `apps.blog`. Create posts in the Django admin; nothing is seeded.

## URLs

| Path | Behaviour |
|---|---|
| `/blog/` | Published posts, newest first, paginated (10 per page) |
| `/blog/<slug>/` | Post detail. Drafts 404 for the public; staff see a "Draft" banner |
| `/blog/feed/` | Atom feed of published posts |
| `/sitemap.xml` | Landing page, blog index, and published posts |
| `/robots.txt` | Allows crawling and points at the sitemap |

The header nav includes a **Blog** link (API docs stay hidden under 30rem width so the bar
fits on a 390px viewport).

## Content

`Post` fields: title, unique slug (prepopulated in admin), summary, Markdown body, optional
author, status (`draft` / `published`), `published_at`, `updated_at`, optional meta
description. Publishing with an empty `published_at` sets it to now.

Body Markdown is rendered with the `markdown` package and sanitised with `nh3`: no scripts,
event handlers, or `javascript:` links; links get `rel="noopener nofollow"`.
