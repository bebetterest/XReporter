from xreporter.models import ActivityType
from xreporter.normalizer import normalize_timeline
from xreporter.x_api import TimelinePayload


ACTOR = {"id": "10", "username": "alice", "name": "Alice"}
ORIGINAL = {
    "id": "99",
    "author_id": "30",
    "text": "original post",
    "created_at": "2026-03-10T01:00:00Z",
    "public_metrics": {"like_count": 10, "retweet_count": 2, "reply_count": 1, "quote_count": 0},
}


def test_activity_classification_and_original_linkage() -> None:
    payload = TimelinePayload(
        tweets=[
            {
                "id": "201",
                "author_id": "10",
                "text": "retweet event",
                "created_at": "2026-03-10T02:00:00Z",
                "referenced_tweets": [{"type": "retweeted", "id": "99"}],
                "public_metrics": {"like_count": 1, "retweet_count": 0, "reply_count": 0, "quote_count": 0},
            },
            {
                "id": "202",
                "author_id": "10",
                "text": "quote event",
                "created_at": "2026-03-10T02:10:00Z",
                "referenced_tweets": [{"type": "quoted", "id": "99"}],
                "public_metrics": {"like_count": 2, "retweet_count": 0, "reply_count": 0, "quote_count": 1},
            },
            {
                "id": "203",
                "author_id": "10",
                "text": "reply event",
                "created_at": "2026-03-10T02:20:00Z",
                "referenced_tweets": [{"type": "replied_to", "id": "99"}],
                "public_metrics": {"like_count": 0, "retweet_count": 0, "reply_count": 1, "quote_count": 0},
            },
            {
                "id": "204",
                "author_id": "10",
                "text": "plain tweet",
                "created_at": "2026-03-10T02:30:00Z",
                "public_metrics": {"like_count": 5, "retweet_count": 1, "reply_count": 1, "quote_count": 0},
            },
        ],
        include_users={"30": {"id": "30", "username": "origin", "name": "Origin"}},
        include_tweets={"99": ORIGINAL},
    )

    batch = normalize_timeline(ACTOR, payload)

    activities = {item.id: item for item in batch.activities}
    assert activities["201"].activity_type == ActivityType.RETWEET
    assert activities["202"].activity_type == ActivityType.QUOTE
    assert activities["203"].activity_type == ActivityType.REPLY
    assert activities["204"].activity_type == ActivityType.TWEET

    assert activities["201"].original_tweet_id == "99"
    assert activities["202"].original_tweet_id == "99"
    assert activities["203"].original_tweet_id == "99"
    assert activities["204"].original_tweet_id is None
