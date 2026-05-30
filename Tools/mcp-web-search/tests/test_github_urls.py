import pytest

from custom_domains.github import _repo_parts, is_github_url
from custom_domains.router import get_custom_route


def test_is_github_url() -> None:
    assert is_github_url("https://github.com/python/cpython")
    assert not is_github_url("https://raw.githubusercontent.com/python/cpython/main/README.md")


def test_repo_parts_blob_rst() -> None:
    url = "https://github.com/python/cpython/blob/main/Doc/whatsnew/3.13.rst"
    parsed = _repo_parts(url)
    assert parsed is not None
    owner, repo, rest = parsed
    assert owner == "python"
    assert repo == "cpython"
    assert rest[:2] == ["blob", "main"]
    assert "/".join(rest[2:]) == "Doc/whatsnew/3.13.rst"


def test_custom_route_matches_github_blob() -> None:
    url = "https://github.com/python/cpython/blob/main/Doc/whatsnew/3.13.rst"
    route = get_custom_route(url)
    assert route is not None
    assert route.name == "github"


@pytest.mark.live
@pytest.mark.asyncio
async def test_fetch_github_page_blob_rst_live() -> None:
    """Optional live check — needs network and GitHub API/raw access."""
    from custom_domains.github import fetch_github_page

    url = "https://github.com/python/cpython/blob/main/Doc/whatsnew/3.13.rst"
    text = await fetch_github_page(url, timeout=25.0)
    assert not text.lstrip().lower().startswith("error:")
    assert "What's New In Python 3.13" in text or "What" in text
    assert len(text) > 5000
