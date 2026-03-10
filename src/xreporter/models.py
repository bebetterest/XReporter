from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class ActivityType(StrEnum):
    TWEET = "tweet"
    RETWEET = "retweet"
    QUOTE = "quote"
    REPLY = "reply"


@dataclass(frozen=True)
class TimeRange:
    since: datetime
    until: datetime


@dataclass
class UserRecord:
    id: str
    username: str
    name: str
    raw_json: dict[str, Any]


@dataclass
class TweetRecord:
    id: str
    author_id: str | None
    text: str
    created_at: datetime | None
    url: str
    like_count: int
    retweet_count: int
    reply_count: int
    quote_count: int
    links: list[str] = field(default_factory=list)
    raw_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActivityRecord:
    id: str
    actor_id: str
    activity_type: ActivityType
    event_tweet_id: str
    event_created_at: datetime | None
    event_text: str
    event_url: str
    original_tweet_id: str | None
    original_author_id: str | None
    original_text: str | None
    original_url: str | None
    like_count: int
    retweet_count: int
    reply_count: int
    quote_count: int
    raw_event_json: dict[str, Any]
    raw_original_json: dict[str, Any] | None


@dataclass
class CollectionRun:
    id: int
    username: str
    target_user_id: str
    since_utc: datetime
    until_utc: datetime
    include_replies: bool
    following_cap: int
    status: str
    total_followings: int
    total_activities: int
