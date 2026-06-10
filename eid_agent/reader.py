from __future__ import annotations

import base64
import contextlib
import datetime as dt
import inspect
import logging
from typing import Any

from eid_agent.errors import AgentError

logger = logging.getLogger(__name__)

DEFAULT_FIELDS = [
    "first_name",
    "first_names",
    "last_name",
    "birth_date",
    "birth_place",
    "national_number",
    "nationality",
    "sex",
    "card_number",
    "issuing_municipality",
    "validity_start",
    "validity_end",
    "address_street",
    "address_zip",
    "address_city",
]

ALLOWED_FIELDS = set(DEFAULT_FIELDS)

FIELD_ALIASES = {
    "first_name": "first_name",
    "first_names": "first_names",
    "firstnames": "first_names",
    "firstname": "first_name",
    "given_name": "first_name",
    "givenname": "first_name",
    "name_first": "first_name",
    "last_name": "last_name",
    "lastname": "last_name",
    "surname": "last_name",
    "family_name": "last_name",
    "name_last": "last_name",
    "national_number": "national_number",
    "nationalnumber": "national_number",
    "rrn": "national_number",
    "niss": "national_number",
    "ssin": "national_number",
    "birth_date": "birth_date",
    "birthdate": "birth_date",
    "date_of_birth": "birth_date",
    "dob": "birth_date",
    "birth_place": "birth_place",
    "birthplace": "birth_place",
    "place_of_birth": "birth_place",
    "nationality": "nationality",
    "sex": "sex",
    "gender": "sex",
    "card_number": "card_number",
    "cardnumber": "card_number",
    "issuing_municipality": "issuing_municipality",
    "municipality_of_issue": "issuing_municipality",
    "validity_start": "validity_start",
    "validity_begin": "validity_start",
    "valid_from": "validity_start",
    "validity_end": "validity_end",
    "valid_to": "validity_end",
    "address": "address_street",
    "address_street": "address_street",
    "street": "address_street",
    "street_name": "address_street",
    "streetnumber": "address_street_number",
    "street_number": "address_street_number",
    "house_number": "address_street_number",
    "address_zip": "address_zip",
    "zip": "address_zip",
    "zipcode": "address_zip",
    "postal_code": "address_zip",
    "address_city": "address_city",
    "city": "address_city",
    "municipality": "address_city",
    "town": "address_city",
    "photo": "photo_base64",
    "picture": "photo_base64",
    "image": "photo_base64",
    "photo_data": "photo_base64",
    "photo_base64": "photo_base64",
}


def _to_snake(value: str) -> str:
    normalized = []
    prev_was_sep = False
    for char in value.strip():
        if char.isalnum():
            if char.isupper() and normalized and not prev_was_sep:
                normalized.append("_")
            normalized.append(char.lower())
            prev_was_sep = False
        else:
            if normalized and not prev_was_sep:
                normalized.append("_")
            prev_was_sep = True
    while normalized and normalized[-1] == "_":
        normalized.pop()
    return "".join(normalized)


def _normalize_birth_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def _normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def _normalize_photo(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


class PythonBeIDBackend:
    def __init__(self) -> None:
        self._module = None
        self._card_reader_cls = None
        self._no_reader_error_cls = None
        self._no_card_error_cls = None

    def _load_library(self) -> None:
        try:
            import pythonbeid  # type: ignore
        except Exception as exc:  # pragma: no cover - import depends on runtime env
            if logger.isEnabledFor(logging.DEBUG):
                logger.exception("Unable to import pythonbeid.")
            else:
                logger.error("Unable to import pythonbeid: %s", exc)
            raise AgentError(500, "INTERNAL_ERROR", "pythonbeid is not available.", str(exc)) from exc

        self._module = pythonbeid
        self._card_reader_cls = getattr(pythonbeid, "CardReader", None)
        exceptions_module = getattr(pythonbeid, "exceptions", None)
        if exceptions_module is not None:
            self._no_reader_error_cls = getattr(exceptions_module, "NoReaderError", None)
            self._no_card_error_cls = getattr(exceptions_module, "NoCardError", None)
        if self._card_reader_cls is None:
            raise AgentError(500, "INTERNAL_ERROR", "pythonbeid.CardReader is not available.")

    @contextlib.contextmanager
    def _open_reader(self):
        reader = self._card_reader_cls()
        enter = getattr(reader, "__enter__", None)
        exit_ = getattr(reader, "__exit__", None)
        if callable(enter) and callable(exit_):
            with reader as managed_reader:
                yield managed_reader
            return
        try:
            yield reader
        finally:
            close = getattr(reader, "close", None)
            if callable(close):
                close()

    def _translate_exception(self, exc: Exception) -> AgentError:
        if self._no_reader_error_cls and isinstance(exc, self._no_reader_error_cls):
            return AgentError(503, "NO_READER", "No smart card reader detected.")
        if self._no_card_error_cls and isinstance(exc, self._no_card_error_cls):
            return AgentError(503, "NO_CARD", "No eID card detected.")
        return AgentError(500, "INTERNAL_ERROR", "Failed to access eID data.")

    def status(self) -> dict[str, Any]:
        self._ensure_loaded()
        readers = self._list_readers()
        has_reader = bool(readers)
        has_card = False

        if has_reader:
            try:
                with self._open_reader() as reader:
                    has_card = self._detect_card_presence(reader)
            except Exception as exc:
                translated = self._translate_exception(exc)
                if translated.code == "NO_CARD":
                    has_card = False
                elif translated.code == "NO_READER":
                    has_reader = False
                    readers = []
                else:
                    # Communication errors (e.g. unresponsive card) must not
                    # turn a diagnostic endpoint into a 500: report the card
                    # as absent and keep the details in the logs.
                    has_card = False
                    if logger.isEnabledFor(logging.DEBUG):
                        logger.exception("Unable to inspect card status.")
                    else:
                        logger.warning("Unable to inspect card status: %s", exc)

        return {
            "has_reader": has_reader,
            "has_card": has_card,
            "readers": readers,
        }

    def _list_readers(self) -> list[str]:
        candidates: list[Any] = []
        for attr in ("list_readers", "get_readers"):
            fn = getattr(self._module, attr, None)
            if callable(fn):
                candidates.append(fn)
        class_list_fn = getattr(self._card_reader_cls, "list_readers", None)
        if callable(class_list_fn):
            candidates.append(class_list_fn)

        for fn in candidates:
            try:
                value = fn()
            except Exception:
                continue
            if isinstance(value, (list, tuple)):
                return [str(item) for item in value]
        return self._pcsc_list_readers()

    @staticmethod
    def _pcsc_list_readers() -> list[str]:
        # Fallback for pythonbeid < 0.3.0, which has no list_readers API.
        # pyscard is a hard dependency of pythonbeid, so it is available here.
        try:
            from smartcard.System import readers as pcsc_readers
        except Exception:
            return []
        try:
            return [str(item) for item in pcsc_readers()]
        except Exception:
            return []

    def _detect_card_presence(self, reader: Any) -> bool:
        for attr in ("has_card", "card_present", "is_card_present", "is_card_inserted"):
            value = getattr(reader, attr, None)
            if callable(value):
                try:
                    return bool(value())
                except Exception:
                    continue
            if isinstance(value, bool):
                return value
        # No introspection attribute available: pythonbeid's CardReader raises
        # NoCardError at construction when no card is present, so an open
        # reader implies a card.
        return True

    def read(self, include_photo: bool = False) -> dict[str, Any]:
        self._ensure_loaded()
        try:
            with self._open_reader() as reader:
                raw_payload = self._invoke_read_method(reader, include_photo)
        except Exception as exc:
            raise self._translate_exception(exc) from exc

        normalized = self._normalize_payload(raw_payload)
        photo_key_present = "photo_base64" in normalized
        if include_photo:
            normalized.setdefault("photo_base64", None)
            if normalized["photo_base64"] is not None:
                normalized.setdefault("photo_mime", "image/jpeg")
        elif photo_key_present:
            normalized["photo_base64"] = None
            normalized.pop("photo_mime", None)
        return normalized

    def _ensure_loaded(self) -> None:
        if self._module is None:
            self._load_library()

    def _invoke_read_method(self, reader: Any, include_photo: bool) -> Any:
        methods = ["read_informations", "read_information", "read_info", "read"]
        kwargs_attempts = [
            {"photo": include_photo},
            {"include_photo": include_photo},
            {"with_photo": include_photo},
            {},
        ]

        for method_name in methods:
            method = getattr(reader, method_name, None)
            if not callable(method):
                continue
            sig = None
            try:
                sig = inspect.signature(method)
            except (TypeError, ValueError):
                sig = None
            for kwargs in kwargs_attempts:
                if sig is not None:
                    filtered_kwargs = {
                        name: value for name, value in kwargs.items() if name in sig.parameters
                    }
                else:
                    filtered_kwargs = kwargs
                try:
                    return method(**filtered_kwargs)
                except TypeError:
                    continue
        raise AgentError(500, "INTERNAL_ERROR", "No supported read method found in pythonbeid.")

    def _normalize_payload(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, dict):
            source = payload
        else:
            source = {
                key: value
                for key, value in vars(payload).items()
                if not key.startswith("_")
            }

        normalized: dict[str, Any] = {}
        for key, value in source.items():
            key_normalized = _to_snake(str(key))
            target_key = FIELD_ALIASES.get(key_normalized)
            if not target_key:
                continue
            if target_key == "birth_date":
                normalized[target_key] = _normalize_birth_date(value)
                continue
            if target_key in {"validity_start", "validity_end"}:
                normalized[target_key] = _normalize_date(value)
                continue
            if target_key == "photo_base64":
                normalized[target_key] = _normalize_photo(value)
                continue
            if target_key == "address_street" and value is not None:
                normalized[target_key] = str(value).strip()
                continue
            normalized[target_key] = value

        if "address_street" not in normalized:
            street = normalized.get("street")
            number = normalized.get("address_street_number")
            if street:
                merged = f"{street} {number}".strip() if number else str(street)
                normalized["address_street"] = merged

        if "first_name" not in normalized and normalized.get("first_names"):
            normalized["first_name"] = str(normalized["first_names"]).split(" ")[0].strip()

        normalized.pop("address_street_number", None)
        return normalized
