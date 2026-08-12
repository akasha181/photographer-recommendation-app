"""
Restore the wishlist uniqueness guards on MySQL.

Unlike bookings, this needs no generated column. MySQL unique indexes already
ignore NULL, and a wishlist row has exactly one of photographer_id /
product_id set (enforced by ck_wishlist_exactly_one_target). So a plain
composite unique index gives precisely the intended behaviour:

    (user=7, photographer=12, product=NULL)  → unique on (user, photographer)
    (user=7, photographer=NULL, product=88)  → the NULL makes this row exempt
                                               from the photographer index

Django skipped these because they were declared with a `condition`; declaring
them unconditionally in SQL is both simpler and correct here.
"""

from django.db import migrations

FORWARD = """
ALTER TABLE wishlist_items
  ADD CONSTRAINT uniq_wishlist_photographer UNIQUE (user_id, photographer_id),
  ADD CONSTRAINT uniq_wishlist_product UNIQUE (user_id, product_id);
"""

REVERSE = """
ALTER TABLE wishlist_items
  DROP INDEX uniq_wishlist_photographer,
  DROP INDEX uniq_wishlist_product;
"""


class Migration(migrations.Migration):
    dependencies = [("wishlist", "0001_initial")]

    operations = [
        migrations.RunSQL(sql=FORWARD, reverse_sql=REVERSE),
    ]
