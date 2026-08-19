"""
Free up completed bookings so a demo account can exercise the review flow.

    python manage.py free_reviews --buyer buyer1@snapsphere.pk --count 3

WHY THIS EXISTS
---------------
`seed_data` writes a review for almost every completed booking, because a
photographer with 410 delivered shoots and 3 reviews looks like a broken
platform. The side effect is that the documented test account
(`buyer1@snapsphere.pk`) has 216 completed bookings and NOTHING left to review —
so the one screen Module 9 exists for opens empty on the account the docs tell
you to log in with.

This removes the review from the N most recent of a buyer's completed bookings
and puts the entitlement back, which is the smallest change that makes the flow
demonstrable.

WHY IT GOES THROUGH THE RATING RECOMPUTE
----------------------------------------
Deleting review rows with `.delete()` alone would leave every affected
photographer's `avg_rating` and `reviews_count` describing reviews that no
longer exist — exactly the disagreement between the headline number and the list
underneath it that `create_review` takes a transaction to prevent. So each
affected profile is refreshed afterwards, in the same transaction.

It also clears `Booking.has_review`, which is deliberately NOT something the
application does (see §12: withdrawing a review does not restore the
entitlement). That asymmetry is why this is a management command and not a
service function: it is a data fixture, not a business operation.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Clear reviews from a buyer's recent completed bookings so they can be re-reviewed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--buyer",
            default="buyer1@snapsphere.pk",
            help="Email of the buyer to free up. Defaults to the documented test account.",
        )
        parser.add_argument(
            "--count", type=int, default=3, help="How many bookings to free."
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing.",
        )

    def handle(self, *args, **options):
        from apps.bookings.constants import BookingStatus
        from apps.bookings.models import Booking
        from apps.profiles.services import refresh_photographer_rating
        from apps.reviews.models import Review, ReviewReply

        User = get_user_model()
        email = options["buyer"]
        count = max(1, options["count"])

        buyer = User.objects.filter(email=email).first()
        if buyer is None:
            raise CommandError(f"No user with email {email!r}.")

        already = Booking.objects.filter(
            buyer=buyer, status=BookingStatus.COMPLETED, has_review=False
        ).count()

        targets = list(
            Booking.objects.filter(
                buyer=buyer, status=BookingStatus.COMPLETED, has_review=True
            )
            .select_related("photographer", "service")
            .order_by("-event_date")[:count]
        )

        if not targets:
            self.stdout.write(
                self.style.WARNING(
                    f"{email} has no reviewed completed bookings to free. "
                    f"{already} are already awaiting a review."
                )
            )
            return

        self.stdout.write(f"{email} — freeing {len(targets)} booking(s):")
        for booking in targets:
            self.stdout.write(
                f"  · {booking.event_date}  {booking.photographer.display_name}"
                f"  ({booking.service.title})"
            )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\nDry run — nothing written."))
            return

        with transaction.atomic():
            affected_profiles = set()
            for booking in targets:
                review = Review.all_objects.filter(booking=booking).first()
                if review is not None:
                    affected_profiles.add(review.photographer)
                    ReviewReply.objects.filter(review=review).delete()
                    review.hard_delete()
                Booking.objects.filter(pk=booking.pk).update(has_review=False)

            # The headline number must never describe reviews that no longer
            # exist. One refresh per affected photographer, not per review.
            for profile in affected_profiles:
                refresh_photographer_rating(profile)

            written = Review.objects.visible().filter(buyer=buyer).count()
            from apps.profiles.models import BuyerProfile

            BuyerProfile.objects.filter(user=buyer).update(reviews_written=written)

        now_pending = Booking.objects.filter(
            buyer=buyer, status=BookingStatus.COMPLETED, has_review=False
        ).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. {email} now has {now_pending} booking(s) awaiting a review "
                f"— visible at GET /reviews/pending/ and on the app's Reviews screen."
            )
        )
        for profile in sorted(affected_profiles, key=lambda p: p.pk):
            profile.refresh_from_db()
            self.stdout.write(
                f"  {profile.display_name}: now {profile.reviews_count} reviews, "
                f"avg {profile.avg_rating}"
            )
