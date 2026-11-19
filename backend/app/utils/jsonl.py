"""JSONL parsing utility."""

import json


class InvalidJSONLError(Exception):
    """Raised when a JSONL byte blob cannot be fully parsed.

    Attributes
    ----------
    line_number : int
        1-indexed line number where the failure was detected (matches what a
        human sees when they open the file in an editor).
    reason : str
        Human-readable description of the failure.
    """

    def __init__(self, line_number: int, reason: str) -> None:
        self.line_number = line_number
        self.reason = reason
        super().__init__(f"Line {line_number}: {reason}")


def parse_jsonl(data: bytes) -> list[dict]:
    """Parse a JSONL byte blob into a list of dicts.

    Processing rules
    ----------------
    1. Decode the bytes as UTF-8 — invalid byte sequences raise
       :class:`InvalidJSONLError` with a clear message.
    2. Split on newlines (both ``\\n`` and ``\\r\\n`` are handled via
       ``splitlines()``).
    3. Skip lines that are blank or contain only whitespace.
    4. Parse each non-blank line with :func:`json.loads`.
    5. Any JSON parse failure raises :class:`InvalidJSONLError` carrying
       the 1-indexed line number and the underlying error message.

    Returns a list of :class:`dict` objects — no schema validation is
    performed here; that is the service layer's responsibility.

    Parameters
    ----------
    data : bytes
        Raw file bytes as received from the upload.

    Returns
    -------
    list[dict]
        Parsed rows, in file order.  Empty when the input is empty or
        contains only blank lines.

    Raises
    ------
    InvalidJSONLError
        On invalid UTF-8, or on any line that cannot be parsed as JSON.
    """
    # Step 1 — UTF-8 decode
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidJSONLError(
            line_number=0,
            reason=f"File is not valid UTF-8: {exc}",
        ) from exc

    rows: list[dict] = []

    # Step 2 — split; splitlines() handles \n, \r\n, and \r uniformly
    # We track the original 1-indexed position for error messages.
    for line_number, line in enumerate(text.splitlines(), start=1):
        # Step 3 — skip blank / whitespace-only lines
        stripped = line.strip()
        if not stripped:
            continue

        # Step 4 — parse JSON
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise InvalidJSONLError(
                line_number=line_number,
                reason=str(exc),
            ) from exc

        # Each row must be a JSON object (dict), not an array or scalar.
        if not isinstance(obj, dict):
            raise InvalidJSONLError(
                line_number=line_number,
                reason=(
                    f"Expected a JSON object ({{...}}) but got "
                    f"{type(obj).__name__}"
                ),
            )

        rows.append(obj)

    return rows
