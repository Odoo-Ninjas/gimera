"""A failed fetch must not leave the cache pointing to the fallback url.

Seen on a CICD host: the ssh fetch of a private repo failed once, gimera
tried the https form, that failed too, and origin stayed at https. Every
later checkout then died in _ensure_sha with "could not read Username for
'https://github.com'".
"""

import subprocess
from types import SimpleNamespace

import pytest

from .. import fetch
from ..cachedir import _sync_origin_url
from ..repo import Repo

SSH_URL = "git@github.com:Odoo-Ninjas/private-repo.git"
HTTPS_URL = "https://github.com/Odoo-Ninjas/private-repo.git"


def _origin(path):
    return subprocess.check_output(
        ["git", "-C", str(path), "remote", "get-url", "origin"], text=True
    ).strip()


@pytest.fixture
def bare_repo(tmp_path):
    path = tmp_path / "cache"
    subprocess.check_call(["git", "init", "-q", "--bare", str(path)])
    subprocess.check_call(["git", "-C", str(path), "remote", "add", "origin", SSH_URL])
    return Repo(path)


def test_failed_fallback_restores_original_url(bare_repo, monkeypatch):
    def always_fails(repo, repo_yml, remote_name, url, filter_remote=None):
        repo.set_remote_url(remote_name, url)
        raise Exception(f"fetch failed for {url}")

    monkeypatch.setattr(fetch, "_set_url_and_fetch", always_fails)
    repo_yml = SimpleNamespace(url=SSH_URL, branch="main")

    with pytest.raises(Exception, match=SSH_URL):
        fetch._fetch_branch(bare_repo, repo_yml)

    assert _origin(bare_repo.path) == SSH_URL


def test_successful_fallback_keeps_working_url(bare_repo, monkeypatch):
    def only_https_works(repo, repo_yml, remote_name, url, filter_remote=None):
        repo.set_remote_url(remote_name, url)
        if url.startswith("git@"):
            raise Exception("ssh down")

    monkeypatch.setattr(fetch, "_set_url_and_fetch", only_https_works)
    repo_yml = SimpleNamespace(url=SSH_URL, branch="main")

    fetch._fetch_branch(bare_repo, repo_yml)

    assert _origin(bare_repo.path) == HTTPS_URL


def test_sync_origin_url_heals_a_broken_cache(bare_repo):
    bare_repo.set_remote_url("origin", HTTPS_URL)

    _sync_origin_url(bare_repo, SSH_URL)

    assert _origin(bare_repo.path) == SSH_URL


def test_sync_origin_url_leaves_matching_url_alone(bare_repo):
    _sync_origin_url(bare_repo, SSH_URL)

    assert _origin(bare_repo.path) == SSH_URL
