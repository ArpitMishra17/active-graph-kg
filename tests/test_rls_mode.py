"""Unit tests for RLS_MODE resolution and detection."""

from __future__ import annotations

import activekg.graph.repository as repo_module
from activekg.graph.repository import GraphRepository


class DummyLogger:
    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


class FakeCursor:
    def __init__(self, row):
        self._row = row

    def execute(self, *args, **kwargs):
        return None

    def fetchone(self):
        return self._row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConn:
    def __init__(self, row):
        self._row = row

    def cursor(self):
        return FakeCursor(self._row)


class FakePool:
    def __init__(self, row):
        self._row = row
        self.put_back = False

    def getconn(self):
        return FakeConn(self._row)

    def putconn(self, conn):
        self.put_back = True


def _repo_with_detect_result(detect_value: bool):
    repo = GraphRepository.__new__(GraphRepository)
    repo.logger = DummyLogger()
    repo._detect_rls = lambda: detect_value
    return repo


def test_detect_rls_true():
    repo = GraphRepository.__new__(GraphRepository)
    repo.pool = FakePool((True,))
    repo.logger = DummyLogger()
    assert repo._detect_rls() is True


def test_detect_rls_false():
    repo = GraphRepository.__new__(GraphRepository)
    repo.pool = FakePool((False,))
    repo.logger = DummyLogger()
    assert repo._detect_rls() is False


def test_detect_rls_no_row():
    repo = GraphRepository.__new__(GraphRepository)
    repo.pool = FakePool(None)
    repo.logger = DummyLogger()
    assert repo._detect_rls() is False


def test_resolve_rls_mode_auto_db_on(monkeypatch):
    repo = _repo_with_detect_result(True)
    monkeypatch.setattr(repo_module, "RLS_MODE", "auto")
    assert repo._resolve_rls_mode() is True


def test_resolve_rls_mode_auto_db_off(monkeypatch):
    repo = _repo_with_detect_result(False)
    monkeypatch.setattr(repo_module, "RLS_MODE", "auto")
    assert repo._resolve_rls_mode() is False


def test_resolve_rls_mode_on(monkeypatch):
    repo = _repo_with_detect_result(False)
    monkeypatch.setattr(repo_module, "RLS_MODE", "on")
    assert repo._resolve_rls_mode() is True


def test_resolve_rls_mode_off_db_off(monkeypatch):
    repo = _repo_with_detect_result(False)
    monkeypatch.setattr(repo_module, "RLS_MODE", "off")
    assert repo._resolve_rls_mode() is False


def test_resolve_rls_mode_off_db_on_forces_on(monkeypatch):
    repo = _repo_with_detect_result(True)
    monkeypatch.setattr(repo_module, "RLS_MODE", "off")
    assert repo._resolve_rls_mode() is True


def test_resolve_rls_mode_unknown_defaults_to_db(monkeypatch):
    repo = _repo_with_detect_result(True)
    monkeypatch.setattr(repo_module, "RLS_MODE", "weird")
    assert repo._resolve_rls_mode() is True
