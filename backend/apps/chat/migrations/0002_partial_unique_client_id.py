"""
Restore the message deduplication guard on MySQL.

See apps/bookings/migrations/0002 for why this is needed.

The chat client draws a message bubble optimistically and then sends it. On a
flaky connection it retries. `client_id` is the client-generated id that makes
the retry idempotent — without a unique index the retry inserts a duplicate
and the user sees their own message twice.
"""

from django.db import migrations

FORWARD = """
ALTER TABLE messages
  ADD COLUMN client_dedupe_key VARCHAR(96)
    GENERATED ALWAYS AS (
      CASE
        WHEN client_id <> '' THEN CONCAT(conversation_id, '|', client_id)
        ELSE NULL
      END
    ) STORED,
  ADD CONSTRAINT uniq_message_client_id UNIQUE (client_dedupe_key);
"""

REVERSE = """
ALTER TABLE messages
  DROP INDEX uniq_message_client_id,
  DROP COLUMN client_dedupe_key;
"""


class Migration(migrations.Migration):
    dependencies = [("chat", "0001_initial")]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
