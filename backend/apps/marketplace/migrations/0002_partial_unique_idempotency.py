"""
Restore the order idempotency guard on MySQL.

See apps/bookings/migrations/0002 for the full explanation of why conditional
UniqueConstraints vanish on MySQL and how the generated-column idiom restores
them.

Here the guard stops a double-tapped Checkout button from charging the buyer's
wallet twice: the client sends the same Idempotency-Key for both requests, and
the second INSERT is rejected by the database.
"""

from django.db import migrations

FORWARD = """
ALTER TABLE orders
  ADD COLUMN idempotency_lookup VARCHAR(96)
    GENERATED ALWAYS AS (
      CASE
        WHEN idempotency_key <> '' THEN CONCAT(buyer_id, '|', idempotency_key)
        ELSE NULL
      END
    ) STORED,
  ADD CONSTRAINT uniq_order_idempotency UNIQUE (idempotency_lookup);
"""

REVERSE = """
ALTER TABLE orders
  DROP INDEX uniq_order_idempotency,
  DROP COLUMN idempotency_lookup;
"""


class Migration(migrations.Migration):
    dependencies = [("marketplace", "0001_initial")]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
