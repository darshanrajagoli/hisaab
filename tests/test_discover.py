"""Tests for input parsing and channel discovery."""

from hisaab.pipeline.discover import parse_channel_input


class TestInputParsing:
    def test_video_url(self):
        result = parse_channel_input("https://www.youtube.com/watch?v=abc123")
        assert result["type"] == "video"
        assert result["video_id"] == "abc123"

    def test_short_video_url(self):
        result = parse_channel_input("https://youtu.be/abc123")
        assert result["type"] == "video"
        assert result["video_id"] == "abc123"

    def test_channel_handle_url(self):
        result = parse_channel_input("https://www.youtube.com/@TestChannel")
        assert result["type"] == "channel"
        assert result["handle"] == "@TestChannel"

    def test_channel_id_url(self):
        result = parse_channel_input("https://www.youtube.com/channel/UCabc123def456")
        assert result["type"] == "channel"
        assert result["channel_id"] == "UCabc123def456"

    def test_bare_handle(self):
        result = parse_channel_input("@TestChannel")
        assert result["type"] == "channel"
        assert result["handle"] == "@TestChannel"

    def test_bare_channel_id(self):
        result = parse_channel_input("UCabc123def456ghi789jkl")
        assert result["type"] == "channel"
        assert result["channel_id"] == "UCabc123def456ghi789jkl"

    def test_plain_name(self):
        result = parse_channel_input("SomeChannel")
        assert result["type"] == "channel"
        assert result["handle"] == "@SomeChannel"
