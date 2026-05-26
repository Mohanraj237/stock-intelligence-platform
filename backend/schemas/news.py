"""News + announcement schemas."""
from __future__ import annotations
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel


class Sentiment(str, Enum):
    POSITIVE         = "POSITIVE"
    MILDLY_POSITIVE  = "MILDLY_POSITIVE"
    NEUTRAL          = "NEUTRAL"
    MILDLY_NEGATIVE  = "MILDLY_NEGATIVE"
    NEGATIVE         = "NEGATIVE"


class NewsItem(BaseModel):
    title: str
    summary: Optional[str] = None
    url: Optional[str] = None
    published: Optional[str] = None
    source: str
    sentiment: Sentiment = Sentiment.NEUTRAL


class AnnouncementItem(BaseModel):
    symbol: str
    subject: str
    desc: Optional[str] = None
    date: Optional[str] = None
    attachment_url: Optional[str] = None
    sentiment: Sentiment = Sentiment.NEUTRAL
