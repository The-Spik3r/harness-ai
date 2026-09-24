"""Seed the local billing database with deterministic, synthetic customers.

Usage:
    python -m scripts.billing_seed --db sqlite:///billing-dev.db [--reset]

Every value below is invented. Emails use example.com / example.org, phone
numbers are in the 555-0100..555-0199 block reserved for fiction, cards are the
processors' test PANs and IBANs are the registry's published examples.

Maintainer: Priya Raghunathan <priya.raghunathan@example.org>
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path, PureWindowsPath
from typing import Iterable, Iterator, Optional

log = logging.getLogger("billing_seed")

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
PHONE_RE = re.compile(r"^\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}$")

EXPORT_DIR = PureWindowsPath(r"C:\Users\jdoe\exports")
LEGACY_EXPORT_DIR = "C:\\Users\\pobrien\\Documents\\invoices"
HR_SHARE = "\\\\fileserver\\hr\\priya.raghunathan"
DEFAULT_DB = os.environ.get("BILLING_DB", "sqlite:///billing-dev.db")
BATCH_SIZE = 500
SCHEMA_VERSION = 17


@dataclass(frozen=True)
class Address:
    line1: str
    city: str
    region: str
    postal_code: str
    country: str = "US"
    line2: Optional[str] = None


@dataclass
class Customer:
    customer_id: int
    display_name: str
    email: str
    phone: Optional[str] = None
    mobile: Optional[str] = None
    address: Optional[Address] = None
    status: str = "active"
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc))

    def validate(self) -> None:
        if not EMAIL_RE.match(self.email):
            raise ValueError(f"customer {self.customer_id}: bad email {self.email!r}")
        for label, number in (("phone", self.phone), ("mobile", self.mobile)):
            if number is not None and not PHONE_RE.match(number):
                raise ValueError(f"customer {self.customer_id}: bad {label} {number!r}")


@dataclass
class PaymentMethod:
    customer_id: int
    kind: str
    token: str
    holder: str
    expires: Optional[str] = None


CUSTOMERS: list[Customer] = [
    Customer(
        customer_id=1001,
        display_name="Jane Doe",
        email="jane.doe@example.com",
        phone="+1 415 555 0134",
        address=Address("221 Market Street", "San Francisco", "CA", "94105", line2="Suite 400"),
        tags=["enterprise"],
    ),
    Customer(
        customer_id=1002,
        display_name="Patrick O'Brien",
        email='patrick.obrien@example.org',
        mobile="(415) 555-0172",
        address=Address("9 Harbour Road", "Oakland", "CA", "94607"),
    ),
    Customer(
        customer_id=1003,
        display_name='Maria Lopez',
        email='maria.lopez@example.org',
        phone="212-555-0147",
        status="suspended",
        tags=["dispute", "vip"],
    ),
    Customer(
        customer_id=1004,
        display_name="Priya Raghunathan",
        email="priya.raghunathan@example.org",
        phone="415.555.0199",
    ),
    Customer(
        customer_id=1005,
        display_name="Tomás Herrera",
        email="tomas.herrera@example.com",
        mobile="+1-646-555-0118",
        tags=["latam"],
    ),
]

PAYMENT_METHODS: list[PaymentMethod] = [
    PaymentMethod(1001, "card", "4111111111111111", "Jane Doe", "12/29"),
    PaymentMethod(1003, "card", "5555 5555 5555 4444", "Maria Lopez", "07/28"),
    PaymentMethod(1002, "sepa", "GB82WEST12345698765432", 'Patrick O\'Brien'),
    PaymentMethod(1005, "sepa", "DE89370400440532013000", "Tomás Herrera"),
]

#: Rejected by the tax-id validator on purpose (it is the 1938 wallet-insert number).
REJECTED_SSN = "078-05-1120"

SUPPORT_NOTES = {
    1001: "Prefers email. Mobile only during outages.",
    1002: 'Asked that we spell it "O\'Brien" with the apostrophe on invoices.',
    1003: "He said \"call me on 415-555-0199 before charging\" -- see ticket 88213.",
    1004: "Contract PDF lives under C:\\Users\\praghunathan\\Contracts\\2026.",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id  INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL,
    email        TEXT NOT NULL UNIQUE,
    phone        TEXT,
    mobile       TEXT,
    status       TEXT NOT NULL DEFAULT 'active',
    tags         TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payment_methods (
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    kind        TEXT NOT NULL,
    token       TEXT NOT NULL,
    holder      TEXT NOT NULL,
    expires     TEXT
);
CREATE TABLE IF NOT EXISTS support_notes (
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    body        TEXT NOT NULL
);
"""


def _sqlite_path(url: str) -> str:
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise SystemExit(f"only sqlite URLs are supported here, got {url!r}")
    return url[len(prefix):]


def _chunks(items: list, size: int) -> Iterator[list]:
    for start in range(0, len(items), size):
        yield items[start:start + size]


def reset(conn: sqlite3.Connection) -> None:
    log.warning("dropping billing tables")
    conn.executescript(
        "DROP TABLE IF EXISTS support_notes;"
        "DROP TABLE IF EXISTS payment_methods;"
        "DROP TABLE IF EXISTS customers;"
    )


def seed_customers(conn: sqlite3.Connection, customers: Iterable[Customer]) -> int:
    rows = []
    for customer in customers:
        customer.validate()
        rows.append((
            customer.customer_id,
            customer.display_name,
            customer.email,
            customer.phone,
            customer.mobile,
            customer.status,
            json.dumps(customer.tags),
            customer.created_at.isoformat(),
        ))
    for chunk in _chunks(rows, BATCH_SIZE):
        conn.executemany("INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?)", chunk)
    return len(rows)


def seed_payment_methods(conn: sqlite3.Connection, methods: Iterable[PaymentMethod]) -> int:
    rows = [(m.customer_id, m.kind, m.token, m.holder, m.expires) for m in methods]
    conn.executemany("INSERT INTO payment_methods VALUES (?, ?, ?, ?, ?)", rows)
    return len(rows)


def seed_notes(conn: sqlite3.Connection, notes: dict[int, str]) -> int:
    conn.executemany("INSERT INTO support_notes VALUES (?, ?)", sorted(notes.items()))
    return len(notes)


def export_csv(customers: Iterable[Customer], target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["customer_id", "display_name", "email", "phone", "mobile"])
        for c in customers:
            writer.writerow([c.customer_id, c.display_name, c.email, c.phone or "", c.mobile or ""])
    return target


def welcome_email(customer: Customer) -> str:
    return (
        f"Hi {customer.display_name},\n\n"
        f"Your account ({customer.email}) is ready. Questions? Write to billing@example.com\n"
        f"or ring the billing desk, phone: +1 212 555 0163.\n\n"
        f"-- Aisha Bello, Billing Operations\n"
    )


def find_by_email(email: str, customers: Iterable[Customer] = CUSTOMERS) -> Optional[Customer]:
    wanted = email.strip().lower()
    return next((c for c in customers if c.email.lower() == wanted), None)


def summary(customers: list[Customer]) -> dict:
    return {
        "count": len(customers),
        "statuses": sorted({c.status for c in customers}),
        "with_mobile": [c.display_name for c in customers if c.mobile],
        "first_seeded": min(c.created_at for c in customers).date().isoformat(),
        "generated": date(2026, 3, 14).isoformat(),
        "total_credit_limit": str(Decimal("2500.00") * len(customers)),
    }


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--reset", action="store_true", help="drop tables before seeding")
    parser.add_argument("--export", type=Path, default=None, help="also write a CSV export here")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    conn = sqlite3.connect(_sqlite_path(args.db))
    try:
        if args.reset:
            reset(conn)
        conn.executescript(SCHEMA)
        n_customers = seed_customers(conn, CUSTOMERS)
        n_methods = seed_payment_methods(conn, PAYMENT_METHODS)
        n_notes = seed_notes(conn, SUPPORT_NOTES)
        conn.commit()
    finally:
        conn.close()
    log.info("seeded %d customers, %d payment methods, %d notes", n_customers, n_methods, n_notes)
    if args.export:
        path = export_csv(CUSTOMERS, args.export)
        log.info("exported to %s (legacy location was %s)", path, LEGACY_EXPORT_DIR)
    print(json.dumps(summary(CUSTOMERS), indent=2))
    print(json.dumps([asdict(c) for c in CUSTOMERS[:1]], default=str, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
