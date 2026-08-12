"""
Restore the top-up replay guard on MySQL.

See apps/bookings/migrations/0002 for the underlying MySQL limitation.

This one is a direct financial control: it makes it impossible to credit the
same bank-transfer reference to a wallet twice, whether through a duplicate
submission by the user or a double-click by the admin approving it.
"""

from django.db import migrations

FORWARD = """
ALTER TABLE topup_requests
  ADD COLUMN approved_reference VARCHAR(110)
    GENERATED ALWAYS AS (
      CASE WHEN status = 'APPROVED' THEN transaction_reference ELSE NULL END
    ) STORED,
  ADD CONSTRAINT uniq_approved_txn_reference UNIQUE (approved_reference);
"""

REVERSE = """
ALTER TABLE topup_requests
  DROP INDEX uniq_approved_txn_reference,
  DROP COLUMN approved_reference;
"""


class Migration(migrations.Migration):
    dependencies = [("profiles", "0001_initial")]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
