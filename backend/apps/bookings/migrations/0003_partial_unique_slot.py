"""
Restore the double-booking guard that MySQL silently dropped.

THE PROBLEM
-----------
Booking.Meta declares:

    UniqueConstraint(
        fields=["photographer", "event_date", "start_time"],
        condition=Q(status__in=["PENDING", "ACCEPTED"]),
        name="uniq_active_booking_slot",
    )

PostgreSQL implements that as a partial unique index. MySQL has no partial
indexes, so Django records the constraint in migration state and creates
NOTHING in the database — without raising an error. The application-level
`SELECT ... FOR UPDATE` check would then be the only thing standing between a
race condition and two paying customers booking the same photographer for the
same wedding.

THE FIX
-------
MySQL unique indexes ignore NULL. So we add a STORED generated column that
holds the slot key only while the booking is live, and NULL otherwise, then
put a plain unique index on it:

    status = PENDING  →  active_slot_key = "12|2026-08-14|14:00:00"  (unique)
    status = CANCELLED → active_slot_key = NULL                      (ignored)

That reproduces partial-unique semantics exactly, and the database — not just
the application — now refuses the second booking.

The same trick is applied in orders, messages, topup_requests and
model_versions (see their 0002 migrations).
"""

from django.db import migrations

FORWARD = """
ALTER TABLE bookings
  ADD COLUMN active_slot_key VARCHAR(96)
    GENERATED ALWAYS AS (
      CASE
        WHEN status IN ('PENDING', 'ACCEPTED') AND is_deleted = 0
          THEN CONCAT(photographer_id, '|', event_date, '|', start_time)
        ELSE NULL
      END
    ) STORED,
  ADD CONSTRAINT uniq_active_booking_slot UNIQUE (active_slot_key);
"""

REVERSE = """
ALTER TABLE bookings
  DROP INDEX uniq_active_booking_slot,
  DROP COLUMN active_slot_key;
"""


class Migration(migrations.Migration):
    dependencies = [("bookings", "0002_initial")]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
