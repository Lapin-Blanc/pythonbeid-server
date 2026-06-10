from __future__ import annotations

from types import SimpleNamespace

import pytest

from eid_agent.reader import PythonBeIDBackend


class DummyCardReader:
    """Stand-in for pythonbeid.CardReader: no introspection API at all."""


def build_backend(module: SimpleNamespace | None = None) -> PythonBeIDBackend:
    backend = PythonBeIDBackend()
    backend._module = module or SimpleNamespace()
    backend._card_reader_cls = DummyCardReader
    return backend


class TestListReaders:
    def test_prefers_module_list_readers(self) -> None:
        module = SimpleNamespace(list_readers=lambda: ["Reader A", "Reader B"])
        backend = build_backend(module)
        assert backend._list_readers() == ["Reader A", "Reader B"]

    def test_falls_back_to_pyscard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import smartcard.System

        monkeypatch.setattr(smartcard.System, "readers", lambda: ["PCSC Reader 0"])
        backend = build_backend()
        assert backend._list_readers() == ["PCSC Reader 0"]

    def test_empty_when_pyscard_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import smartcard.System

        def boom() -> list[str]:
            raise RuntimeError("PC/SC service unavailable")

        monkeypatch.setattr(smartcard.System, "readers", boom)
        backend = build_backend()
        assert backend._list_readers() == []


class TestStatus:
    def test_unresponsive_card_degrades_instead_of_raising(self) -> None:
        class FailingCardReader:
            def __init__(self) -> None:
                raise RuntimeError("Unable to connect with protocol: T0 or T1.")

        module = SimpleNamespace(list_readers=lambda: ["Reader A"])
        backend = build_backend(module)
        backend._card_reader_cls = FailingCardReader
        assert backend.status() == {
            "has_reader": True,
            "has_card": False,
            "readers": ["Reader A"],
        }


class TestDetectCardPresence:
    def test_open_reader_without_introspection_means_card_present(self) -> None:
        backend = build_backend()
        assert backend._detect_card_presence(DummyCardReader()) is True

    def test_explicit_attribute_is_honored(self) -> None:
        backend = build_backend()
        reader = SimpleNamespace(has_card=False)
        assert backend._detect_card_presence(reader) is False

    def test_callable_attribute_is_honored(self) -> None:
        backend = build_backend()
        reader = SimpleNamespace(has_card=lambda: True)
        assert backend._detect_card_presence(reader) is True
