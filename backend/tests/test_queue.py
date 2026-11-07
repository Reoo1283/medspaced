import sys
from types import SimpleNamespace

from app.core.config import settings
from app.services.queue import enqueue_task


class BackgroundTasksStub:
    def __init__(self) -> None:
        self.tasks = []

    def add_task(self, func, *args) -> None:
        self.tasks.append((func, args))
        func(*args)


def test_enqueue_task_defaults_to_inline():
    background = BackgroundTasksStub()
    called = []
    result = enqueue_task(background, "medspaced.process_content", called.append, "a")
    assert result == "inline"
    assert called == ["a"]


def test_enqueue_task_uses_celery(monkeypatch):
    sent = []
    monkeypatch.setattr(settings, "job_queue_backend", "celery")
    monkeypatch.setitem(
        sys.modules,
        "app.worker",
        SimpleNamespace(celery_app=SimpleNamespace(send_task=lambda name, args: sent.append((name, args)))),
    )
    background = BackgroundTasksStub()
    result = enqueue_task(background, "medspaced.process_content", lambda *_: None, "job", "file")
    assert result == "celery"
    assert sent == [("medspaced.process_content", ["job", "file"])]
    assert background.tasks == []


def test_enqueue_task_falls_back_when_celery_fails(monkeypatch):
    monkeypatch.setattr(settings, "job_queue_backend", "celery")

    def broken(name, args):
        raise ConnectionError("redis yok")

    monkeypatch.setitem(
        sys.modules,
        "app.worker",
        SimpleNamespace(celery_app=SimpleNamespace(send_task=broken)),
    )
    background = BackgroundTasksStub()
    called = []
    result = enqueue_task(background, "medspaced.process_content", called.append, "a")
    assert result == "inline"
    assert called == ["a"]
