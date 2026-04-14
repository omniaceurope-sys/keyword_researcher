"""Tests for keyword_researcher/pipeline/keyword_planner.py (no API calls)."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestCaching:
    """Verify cache load/save behaviour without hitting the Google Ads API."""

    def _make_volumes_call(self, keywords, cached_data=None, api_returns=None):
        """Helper: call get_search_volumes with controlled cache and API mock."""
        cache_content = json.dumps(cached_data or {})
        api_returns = api_returns or {}

        with patch("pipeline.keyword_planner._CACHE_PATH") as mock_path, \
             patch("pipeline.keyword_planner._build_client") as mock_build, \
             patch("pipeline.keyword_planner._save_cache") as mock_save:

            mock_path.exists.return_value = bool(cached_data)
            mock_path.read_text.return_value = cache_content

            mock_client = MagicMock()
            mock_build.return_value = mock_client

            # Simulate API returning ideas
            ideas = []
            for kw, vol in api_returns.items():
                idea = MagicMock()
                idea.text = kw
                idea.keyword_idea_metrics.avg_monthly_searches = vol
                ideas.append(idea)
            mock_client.get_service.return_value.generate_keyword_ideas.return_value = ideas

            from pipeline.keyword_planner import get_search_volumes
            result = get_search_volumes(keywords)
            return result, mock_save

    def test_returns_empty_for_empty_input(self):
        from pipeline.keyword_planner import get_search_volumes
        with patch("pipeline.keyword_planner._build_client"):
            assert get_search_volumes([]) == {}

    def test_cached_keywords_skip_api(self):
        cached = {"2840_1000": {"python": 50000, "django": 20000}}
        with patch("pipeline.keyword_planner._CACHE_PATH") as mock_path, \
             patch("pipeline.keyword_planner._build_client") as mock_build, \
             patch("pipeline.keyword_planner._save_cache") as mock_save:

            mock_path.exists.return_value = True
            mock_path.read_text.return_value = json.dumps(cached)

            from pipeline.keyword_planner import get_search_volumes
            result = get_search_volumes(["python", "django"])

        assert result == {"python": 50000, "django": 20000}
        mock_build.assert_not_called()
        mock_save.assert_not_called()

    def test_deduplicates_keywords(self):
        """Duplicate inputs should only be looked up once."""
        cached = {"2840_1000": {"python": 50000}}
        with patch("pipeline.keyword_planner._CACHE_PATH") as mock_path, \
             patch("pipeline.keyword_planner._build_client"), \
             patch("pipeline.keyword_planner._save_cache"):

            mock_path.exists.return_value = True
            mock_path.read_text.return_value = json.dumps(cached)

            from pipeline.keyword_planner import get_search_volumes
            result = get_search_volumes(["python", "Python", "PYTHON"])

        assert len(result) == 1
        assert result["python"] == 50000

    def test_uncached_keywords_call_api_and_save(self):
        cached = {"2840_1000": {"python": 50000}}

        with patch("pipeline.keyword_planner._CACHE_PATH") as mock_path, \
             patch("pipeline.keyword_planner._build_client") as mock_build, \
             patch("pipeline.keyword_planner._save_cache") as mock_save, \
             patch("pipeline.keyword_planner.GOOGLE_ADS_CUSTOMER_ID", "123-456-789"):

            mock_path.exists.return_value = True
            mock_path.read_text.return_value = json.dumps(cached)

            idea = MagicMock()
            idea.text = "flask"
            idea.keyword_idea_metrics.avg_monthly_searches = 10000
            mock_client = MagicMock()
            mock_client.get_service.return_value.generate_keyword_ideas.return_value = [idea]
            mock_build.return_value = mock_client

            from pipeline.keyword_planner import get_search_volumes
            result = get_search_volumes(["python", "flask"])

        assert result["python"] == 50000
        assert result["flask"] == 10000
        mock_save.assert_called_once()

    def test_different_geo_language_uses_separate_cache_key(self):
        cached = {
            "2840_1000": {"python": 50000},
            "2826_1000": {"python": 30000},
        }
        with patch("pipeline.keyword_planner._CACHE_PATH") as mock_path, \
             patch("pipeline.keyword_planner._build_client"), \
             patch("pipeline.keyword_planner._save_cache"):

            mock_path.exists.return_value = True
            mock_path.read_text.return_value = json.dumps(cached)

            from pipeline.keyword_planner import get_search_volumes
            us_result = get_search_volumes(["python"], geo_target_id="2840", language_id="1000")
            uk_result = get_search_volumes(["python"], geo_target_id="2826", language_id="1000")

        assert us_result["python"] == 50000
        assert uk_result["python"] == 30000

    def test_corrupt_cache_falls_back_gracefully(self):
        with patch("pipeline.keyword_planner._CACHE_PATH") as mock_path, \
             patch("pipeline.keyword_planner._build_client") as mock_build, \
             patch("pipeline.keyword_planner._save_cache"), \
             patch("pipeline.keyword_planner.GOOGLE_ADS_CUSTOMER_ID", "123"):

            mock_path.exists.return_value = True
            mock_path.read_text.return_value = "not valid json {"

            idea = MagicMock()
            idea.text = "python"
            idea.keyword_idea_metrics.avg_monthly_searches = 50000
            mock_client = MagicMock()
            mock_client.get_service.return_value.generate_keyword_ideas.return_value = [idea]
            mock_build.return_value = mock_client

            from pipeline.keyword_planner import get_search_volumes
            result = get_search_volumes(["python"])

        assert "python" in result
