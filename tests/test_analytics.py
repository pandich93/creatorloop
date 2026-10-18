from zoneinfo import ZoneInfo

from creatorloop import analytics

TZ = ZoneInfo("Asia/Karachi")

MEDIA = [
    {
        "id": "1",
        "media_type": "VIDEO",
        "media_product_type": "REELS",
        "timestamp": "2026-09-01T10:00:00+0000",
        "like_count": 100,
        "comments_count": 10,
        "view_count": 5000,
        "caption": "Новый ролик #финансы #money",
    },
    {
        "id": "2",
        "media_type": "CAROUSEL_ALBUM",
        "timestamp": "2026-09-04T10:00:00+0000",
        "like_count": 50,
        "comments_count": 5,
        "caption": "#финансы карусель",
    },
    {"id": "3", "media_type": "IMAGE", "timestamp": "2026-09-08T10:00:00+0000", "comments_count": 2, "caption": "likes hidden"},
]


def test_media_format():
    assert [analytics.media_format(m) for m in MEDIA] == ["REELS", "CAROUSEL", "IMAGE"]


def test_hashtags_unicode():
    assert analytics.hashtags("Hi #Финансы and #money_tips!") == ["финансы", "money_tips"]


def test_interactions_hidden_likes():
    assert analytics.interactions(MEDIA[0]) == 110
    assert analytics.interactions(MEDIA[2]) is None


def test_summarize_public_media():
    s = analytics.summarize_public_media(MEDIA, followers=1000, tz=TZ, top_n=1)
    assert s["posts_analyzed"] == 3
    assert s["posts_with_hidden_likes"] == 1
    assert s["er_by_followers_pct"] == 8.25  # avg(110, 55) / 1000
    assert s["top_posts"][0]["id"] == "1"
    assert s["top_hashtags"][0] == {"hashtag": "#финансы", "posts": 2}
    assert s["frequency"]["posts_per_week"] == 3.0


def test_own_engagement_rate():
    assert analytics.own_engagement_rate({"reach": 200, "likes": 10, "comments": 2, "saved": 4, "shares": 4}) == 10.0
    assert analytics.own_engagement_rate({"reach": 0}) is None


def test_follower_growth():
    g = analytics.follower_growth(
        [
            {"captured_on": "2026-09-01", "followers_count": 1000},
            {"captured_on": "2026-09-11", "followers_count": 1100},
        ]
    )
    assert g["change"] == 100 and g["change_pct"] == 10.0 and g["avg_per_day"] == 10.0


def test_best_times_local_timezone():
    bt = analytics.best_times(MEDIA, TZ)
    # 10:00 UTC == 15:00 Karachi
    assert bt["by_hour"][0]["slot"] == 15


def _own(mid, reach, likes, ts="2026-08-01T10:00:00+0000", fmt="CAROUSEL_ALBUM", saved=0, shares=0):
    ins = {"reach": reach, "likes": likes, "comments": 0, "saved": saved, "shares": shares, "views": reach * 2}
    return {"id": mid, "media_type": fmt, "timestamp": ts, "insights": ins, "engagement_rate": analytics.own_engagement_rate(ins)}


def test_weighted_engagement_rate_ignores_tiny_reach_outliers():
    items = [_own("a", 2904, 35, saved=54, shares=93), _own("b", 3, 1)]
    # mean of ratios would be (6.27 + 33.3) / 2 ≈ 19.8; weighted is 183 / 2907
    assert analytics.weighted_engagement_rate(items) == 6.3


def test_young_posts_are_excluded_and_reported():
    from datetime import UTC, datetime, timedelta

    fresh = (datetime.now(UTC) - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    items = [_own(str(i), 100 + i, 10) for i in range(6)] + [_own("new", 1, 0, ts=fresh)]
    report = analytics.summarize_own_media(items, TZ, top_n=2)
    assert report["posts_analyzed"] == 6
    assert [p["id"] for p in report["still_growing"]] == ["new"]
    assert "new" not in [p["id"] for p in report["worst_posts"]]


def test_short_views_fall_back_to_insights():
    assert analytics._short(_own("a", 10, 1))["views"] == 20


def test_viral_posts_by_views_and_interactions():
    media = [
        {
            "id": f"r{i}",
            "media_product_type": "REELS",
            "media_type": "VIDEO",
            "timestamp": "2026-08-01T10:00:00+0000",
            "view_count": v,
            "like_count": 1,
        }
        for i, v in enumerate([100, 120, 90, 110, 900])
    ] + [
        {
            "id": f"c{i}",
            "media_type": "CAROUSEL_ALBUM",
            "timestamp": "2026-08-01T10:00:00+0000",
            "like_count": n,
            "comments_count": 0,
        }
        for i, n in enumerate([10, 12, 11])
    ]
    res = analytics.viral_posts(media, multiplier=3)
    assert [h["id"] for h in res["viral"]] == ["r4"]
    assert res["medians"] == {"views": 110, "interactions": 11}


def test_post_growth_curve():
    history = {
        "media": {"media_id": "x", "published_at": "2026-09-01T00:00:00+0000"},
        "snapshots": [
            {"captured_at": "2026-09-01T12:00:00+00:00", "reach": 100, "views": None},
            {"captured_at": "2026-09-02T12:00:00+00:00", "reach": 300, "views": None},
        ],
    }
    g = analytics.post_growth(history)
    assert g["points"][0]["age_hours"] == 12.0
    assert g["gain_per_day"]["reach"] == 200.0 and g["status"] == "growing"


def test_caption_language_and_features():
    assert analytics.caption_language("Claude Code bilan ishlashda ko'pchilik promptni yaxshilashga urinadi") == "uz"
    assert analytics.caption_language("Что умеет: находит вирусные видео") == "ru"
    assert analytics.caption_language("Ўзбек тилида қисқа матн") == "uz"
    assert analytics.caption_language("How I built it") == "en"
    assert analytics.caption_language("Таксичилик бир бахона эди") == "uz"  # Uzbek in Russian letters
    assert analytics.caption_language("Работаем братья работаем") == "ru"
    f = analytics.caption_features({"caption": "Nega bu ishlamaydi?\n\nSaqlab qo'ying va do'stlaringizga ulashing #ai"})
    assert f["hook"] == "Nega bu ishlamaydi?" and f["hook_is_question"] and f["has_cta"] and f["hashtags"] == 1


def test_conversion_and_reels_watch():
    feed = _own("f", 1000, 10)
    feed["insights"].update(follows=5, profile_visits=20)
    reel = {
        "id": "r",
        "media_product_type": "REELS",
        "media_type": "VIDEO",
        "timestamp": "2026-08-01T10:00:00+0000",
        "caption": "Hook line\nrest",
        "insights": {"reach": 500, "ig_reels_avg_watch_time": 6500, "ig_reels_video_view_total_time": 3_600_000},
    }
    conv = analytics.conversion_by_format([feed, reel])
    assert conv == [
        {"format": "CAROUSEL", "posts": 1, "follows_per_1k_reach": 5.0, "profile_visits_per_1k_reach": 20.0, "total_follows": 5}
    ]
    watch = analytics.reels_watch([reel])
    assert watch["avg_watch_time_s"] == 6.5 and watch["total_watch_hours"] == 1.0
    assert watch["longest_watched"][0]["hook"] == "Hook line"
