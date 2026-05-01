import os
from unittest.mock import MagicMock

os.environ.setdefault("YOUTUBE_API_KEY", "test-youtube-key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("MAX_VIDEOS", "5")
os.environ.setdefault("MAX_TRANSCRIPT_MINUTES", "30")
os.environ.setdefault("CACHE_TTL_SECONDS", "3600")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
os.environ.setdefault("ENVIRONMENT", "test")

import googleapiclient.discovery  # noqa: E402

googleapiclient.discovery.build = MagicMock(return_value=MagicMock())

from google import genai  # noqa: E402

genai.Client = MagicMock(return_value=MagicMock())
