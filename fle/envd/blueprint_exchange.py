"""Lossless, bounded editing of native Factorio blueprint exchange documents.

Keep unknown engine fields: circuitry, schedules, quality, tiles and book
metadata must survive an edit without a parallel schema lagging Factorio.
"""

import base64
import binascii
import json
import zlib

from fle.envd.blueprints import BlueprintInvalid, MAX_BLUEPRINT_BYTES

MAX_DOCUMENT_BYTES = 8 * 1024 * 1024
KINDS = {"blueprint", "blueprint_book", "upgrade_planner", "deconstruction_planner"}


def _document(value):
    if not isinstance(value, dict) or len(KINDS.intersection(value)) != 1:
        raise BlueprintInvalid("Expected one native blueprint, book, or planner")
    kind = next(iter(KINDS.intersection(value)))
    if not isinstance(value[kind], dict):
        raise BlueprintInvalid(f"{kind} must be an object")
    return value


def decode_exchange(content: str) -> dict:
    if not isinstance(content, str) or not content.startswith("0"):
        raise BlueprintInvalid("Expected a Factorio version-0 exchange string")
    if len(content) > MAX_BLUEPRINT_BYTES:
        raise BlueprintInvalid("Exchange string exceeds the blueprint size limit")
    try:
        compressed = base64.b64decode(content[1:], validate=True)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, MAX_DOCUMENT_BYTES + 1)
        if len(raw) > MAX_DOCUMENT_BYTES or not decoder.eof or decoder.unused_data:
            raise BlueprintInvalid("Oversized, incomplete, or trailing blueprint data")
        return _document(json.loads(raw))
    except (
        ValueError,
        UnicodeError,
        binascii.Error,
        zlib.error,
        RecursionError,
    ) as exc:
        raise BlueprintInvalid(f"Invalid blueprint exchange document: {exc}") from exc


def encode_exchange(document: dict) -> str:
    try:
        raw = json.dumps(
            _document(document), separators=(",", ":"), allow_nan=False
        ).encode()
    except (TypeError, ValueError, RecursionError) as exc:
        raise BlueprintInvalid(f"Invalid blueprint document: {exc}") from exc
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise BlueprintInvalid("Blueprint document exceeds the decoded size limit")
    content = "0" + base64.b64encode(zlib.compress(raw)).decode("ascii")
    if len(content) > MAX_BLUEPRINT_BYTES:
        raise BlueprintInvalid("Exchange string exceeds the blueprint size limit")
    return content


def select_blueprint(document: dict, book_path: list[int] | None = None) -> dict:
    """Select native (zero-based) book entry indices, including nested books.

    The selected entry may be a blueprint, a nested book, an upgrade planner or
    a deconstruction planner; the caller decides which leaf kinds it accepts.
    """
    value = _document(document)
    for index in book_path or []:
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise BlueprintInvalid("Book indices must be nonnegative integers")
        book = value.get("blueprint_book")
        if not isinstance(book, dict):
            raise BlueprintInvalid("Book path descends into a non-book entry")
        entries = book.get("blueprints", [])
        if not isinstance(entries, list) or any(
            not isinstance(entry, dict) for entry in entries
        ):
            raise BlueprintInvalid("Book entries must be objects")
        matches = [entry for entry in entries if entry.get("index") == index]
        if len(matches) != 1:
            raise BlueprintInvalid(f"Book entry {index} does not exist or is ambiguous")
        value = {key: val for key, val in matches[0].items() if key != "index"}
    if len(KINDS.intersection(value)) != 1:
        raise BlueprintInvalid(
            "Book entry is not a blueprint, book, upgrade planner, or "
            "deconstruction planner"
        )
    if "blueprint_book" in value:
        raise BlueprintInvalid("Select a nested entry using book_path before using a book")
    return value
