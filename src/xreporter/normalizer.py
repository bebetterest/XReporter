from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from xreporter.models import ActivityRecord, ActivityType, TweetRecord, UserRecord
from xreporter.x_api import TimelinePayload


@dataclass
class NormalizedBatch:
    users: dict[str, UserRecord]
    tweets: dict[str, TweetRecord]
    activities: list[ActivityRecord]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _extract_metrics(tweet: dict[str, Any]) -> tuple[int, int, int, int]:
    metrics = tweet.get("public_metrics", {})
    return (
        int(metrics.get("like_count", 0)),
        int(metrics.get("retweet_count", 0)),
        int(metrics.get("reply_count", 0)),
        int(metrics.get("quote_count", 0)),
    )


def _extract_links(tweet: dict[str, Any]) -> list[str]:
    links: list[str] = []
    entities = tweet.get("entities", {})
    for url_info in entities.get("urls", []):
        for key in ("expanded_url", "unwound_url", "url"):
            value = url_info.get(key)
            if value:
                links.append(str(value))
                break
    return sorted(set(links))


def _status_url(username: str | None, tweet_id: str) -> str:
    if username:
        return f"https://x.com/{username}/status/{tweet_id}"
    return f"https://x.com/i/web/status/{tweet_id}"


def _activity_type(tweet: dict[str, Any]) -> tuple[ActivityType, str | None]:
    activity_type = ActivityType.TWEET
    original_id: str | None = None

    refs = tweet.get("referenced_tweets", [])
    for ref in refs:
        ref_type = ref.get("type")
        ref_id = ref.get("id")
        if ref_type == "retweeted":
            return ActivityType.RETWEET, ref_id

    for ref in refs:
        ref_type = ref.get("type")
        ref_id = ref.get("id")
        if ref_type == "quoted":
            return ActivityType.QUOTE, ref_id

    for ref in refs:
        ref_type = ref.get("type")
        ref_id = ref.get("id")
        if ref_type == "replied_to":
            return ActivityType.REPLY, ref_id

    return activity_type, original_id


def _to_user_record(item: dict[str, Any]) -> UserRecord:
    return UserRecord(
        id=item["id"],
        username=item.get("username", ""),
        name=item.get("name", ""),
        raw_json=item,
    )


def _to_tweet_record(tweet: dict[str, Any], users: dict[str, UserRecord]) -> TweetRecord:
    author_id = tweet.get("author_id")
    author_username = users.get(str(author_id)).username if author_id and str(author_id) in users else None
    like_count, retweet_count, reply_count, quote_count = _extract_metrics(tweet)
    return TweetRecord(
        id=tweet["id"],
        author_id=author_id,
        text=tweet.get("text", ""),
        created_at=_parse_datetime(tweet.get("created_at")),
        url=_status_url(author_username, tweet["id"]),
        like_count=like_count,
        retweet_count=retweet_count,
        reply_count=reply_count,
        quote_count=quote_count,
        links=_extract_links(tweet),
        raw_json=tweet,
    )


def normalize_timeline(actor: dict[str, Any], payload: TimelinePayload) -> NormalizedBatch:
    users: dict[str, UserRecord] = {}

    users[actor["id"]] = _to_user_record(actor)
    for item in payload.include_users.values():
        users[item["id"]] = _to_user_record(item)

    tweets_map: dict[str, dict[str, Any]] = {}
    for item in payload.include_tweets.values():
        tweets_map[item["id"]] = item
    for item in payload.tweets:
        tweets_map[item["id"]] = item

    tweet_records: dict[str, TweetRecord] = {
        tweet_id: _to_tweet_record(tweet_item, users) for tweet_id, tweet_item in tweets_map.items()
    }

    activities: list[ActivityRecord] = []
    for event in payload.tweets:
        event_id = event["id"]
        activity_type, original_id = _activity_type(event)

        original = tweets_map.get(original_id) if original_id else None
        original_author_id = str(original.get("author_id")) if original and original.get("author_id") else None

        actor_record = users.get(actor["id"]) or _to_user_record(actor)
        original_author_username = None
        if original_author_id and original_author_id in users:
            original_author_username = users[original_author_id].username

        like_count, retweet_count, reply_count, quote_count = _extract_metrics(event)

        activities.append(
            ActivityRecord(
                id=event_id,
                actor_id=actor["id"],
                activity_type=activity_type,
                event_tweet_id=event_id,
                event_created_at=_parse_datetime(event.get("created_at")),
                event_text=event.get("text", ""),
                event_url=_status_url(actor_record.username, event_id),
                original_tweet_id=original_id,
                original_author_id=original_author_id,
                original_text=original.get("text") if original else None,
                original_url=_status_url(original_author_username, original_id) if original_id else None,
                like_count=like_count,
                retweet_count=retweet_count,
                reply_count=reply_count,
                quote_count=quote_count,
                raw_event_json=event,
                raw_original_json=original,
            )
        )

    return NormalizedBatch(users=users, tweets=tweet_records, activities=activities)
