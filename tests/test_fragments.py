"""Unit: fragment filter + post-merge path re-resolution."""
from __future__ import annotations

import re

FRAGMENT_RE = re.compile(r"\.f\d+(?:-\d+)?(?:-part)?\.(?:mp4|webm|mkv|m4a|part)$")


def test_fragment_files_are_ignored_by_hook():
    assert FRAGMENT_RE.search("video-OtBAswUpDqg.f251-2.webm")
    assert FRAGMENT_RE.search("video-OtBAswUpDqg.f137.mp4")
    assert FRAGMENT_RE.search("video.f251.m4a")


def test_final_merged_files_pass_the_hook():
    assert not FRAGMENT_RE.search("video-OtBAswUpDqg.mkv")
    assert not FRAGMENT_RE.search("video-uEVipFGa7I0.webm")
    assert not FRAGMENT_RE.search("aula-360-07012026.mp4")
