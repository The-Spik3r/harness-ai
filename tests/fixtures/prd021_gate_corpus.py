"""PRD-021 STORY-007: one two-sentence text per default PII entity, for the gate's T2 loop.

Each entry is `(entity, text, raw)`: a context sentence first, then the sentence
holding the entity `raw`. Every text is at most 90 characters and was probed with
redact() on `en_core_web_sm` (the model the tests pin) to be masked whole. The
module asserts nothing; tests/test_stream_redaction.py asserts, for each entry,
that redact(text) masks `raw`, so a recognizer miss fails loudly instead of
making the T2 loop pass vacuously.
"""

CORPUS = [
    ("PERSON", "Please note the following. Dr. Maria Lopez will join us today.", "Maria Lopez"),
    (
        "EMAIL_ADDRESS",
        "Send the report soon. Write to priya.raghunathan@example.com for it.",
        "priya.raghunathan@example.com",
    ),
    (
        "PHONE_NUMBER",
        "Call us anytime. My phone number is +1 415 555 0134 for urgent cases.",
        "+1 415 555 0134",
    ),
    (
        "CREDIT_CARD",
        "Billing details follow. Charge card 4111 1111 1111 1111 for the refund.",
        "4111 1111 1111 1111",
    ),
    (
        "US_SSN",
        "Identity check next. My social security number is 219-09-9999 today.",
        "219-09-9999",
    ),
    (
        "IBAN_CODE",
        "Payment info follows. Wire it to IBAN GB82 WEST 1234 5698 7654 32 please.",
        "GB82 WEST 1234 5698 7654 32",
    ),
    ("LOCATION", "Travel plans are set. We are flying to Seattle next week.", "Seattle"),
]
