"""
Restore the "exactly one active model per name" guard on MySQL.

See apps/bookings/migrations/0002 for the underlying MySQL limitation.

Without this, a failed promotion could leave two ModelVersion rows for
`ranker` both flagged is_active=True, and which one the engine loads becomes
a coin toss — the worst possible failure mode for a recommendation system,
because it is silent and intermittent.
"""

from django.db import migrations

FORWARD = """
ALTER TABLE model_versions
  ADD COLUMN active_name VARCHAR(40)
    GENERATED ALWAYS AS (CASE WHEN is_active = 1 THEN name ELSE NULL END) STORED,
  ADD CONSTRAINT uniq_active_model_per_name UNIQUE (active_name);
"""

REVERSE = """
ALTER TABLE model_versions
  DROP INDEX uniq_active_model_per_name,
  DROP COLUMN active_name;
"""


class Migration(migrations.Migration):
    dependencies = [("recommendations", "0001_initial")]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
