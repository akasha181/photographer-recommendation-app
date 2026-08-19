"""
Load the real datasets in ml/data/raw/ into the SnapSphere schema.

    python manage.py seed_data --flush

WHY THIS COMMAND EXISTS
-----------------------
The schema is worthless until it holds realistic data. This command turns the
ten CSVs collected during requirement gathering into a working platform:
200 photographers with services and metrics, 244 buyers, 500 bookings derived
from real interaction outcomes, reviews written from an actual review corpus,
12 months of seasonal demand and a year of daily analytics.

Every mapping decision is documented inline, because the mapping is where the
data quality problems live.
"""

import csv
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.text import slugify

from apps.core.constants import CANONICAL_CATEGORIES, PAKISTAN_CITIES, UserRole
from apps.core.review_text import review_text, review_title

# Deterministic seed: re-running the command produces the same demo data, so
# screenshots in the report always match what the examiner sees.
random.seed(20260730)

RAW = Path(settings.ML_DATA_RAW_DIR)

# ─── PKR conversion ──────────────────────────────────────────────────────────
# photographer_profiles.csv prices run 109-1992 (USD-scale). The prototype and
# the target market are Pakistani, so prices are scaled ×100 and rounded to the
# nearest 500 to look like real quoted rates (Rs 10,900 → Rs 11,000).
PKR_MULTIPLIER = 100


def to_pkr(value: float) -> Decimal:
    raw = float(value) * PKR_MULTIPLIER
    return Decimal(str(int(round(raw / 500.0) * 500)))


FIRST_NAMES = [
    "Zara", "Bilal", "Sana", "Omar", "Ayesha", "Kamran", "Hina", "Faisal",
    "Mahnoor", "Usman", "Iqra", "Hamza", "Nimra", "Ahsan", "Areeba", "Talha",
    "Fatima", "Danish", "Rabia", "Shahzad", "Komal", "Adnan", "Mehwish",
    "Junaid", "Sadia", "Bilawal", "Anum", "Waleed", "Laiba", "Zeeshan",
    "Amna", "Salman", "Hafsa", "Rizwan", "Maryam", "Imran", "Noor", "Asad",
]
LAST_NAMES = [
    "Malik", "Raza", "Tariq", "Sheikh", "Noor", "Javed", "Khan", "Ahmed",
    "Hussain", "Iqbal", "Butt", "Qureshi", "Siddiqui", "Chaudhry", "Abbasi",
    "Farooq", "Mirza", "Rehman", "Aslam", "Nawaz", "Bhatti", "Shah", "Gill",
]

SPECIALIZATIONS = {
    "Wedding": ["Bridal Portrait", "Mehndi", "Baraat", "Nikah", "Valima"],
    "Corporate": ["Headshots", "Conference", "Product", "Real Estate", "Team"],
    "Fashion": ["Editorial", "Lookbook", "Runway", "Beauty", "Campaign"],
    "Birthday": ["Kids Party", "Cake Smash", "Candid", "Family", "Newborn"],
    "Graduation": ["Convocation", "Campus", "Group", "Portrait", "Ceremony"],
}


def read_csv(name: str) -> list[dict]:
    path = RAW / name
    if not path.exists():
        raise FileNotFoundError(f"Expected dataset at {path}")
    with path.open(encoding="utf-8", errors="ignore") as fh:
        return list(csv.DictReader(fh))


class Command(BaseCommand):
    help = "Seed the database from the CSV datasets in ml/data/raw/"

    def add_arguments(self, parser):
        parser.add_argument(
            "--flush", action="store_true",
            help="Delete existing seeded data before loading.",
        )
        parser.add_argument(
            "--skip-analytics", action="store_true",
            help="Skip the ~1,800 daily analytics rows (faster for quick runs).",
        )
        parser.add_argument(
            "--skip-history", action="store_true",
            dest="skip_history",
            help="Skip generating the ~50k historical bookings and reviews that "
                 "back each photographer's headline rating (much faster, but "
                 "profiles will show a rating with no reviews behind it).",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\nSnapSphere data seeder"))
        self.stdout.write(f"Reading datasets from {RAW}\n")

        if options["flush"]:
            self._flush()

        self.categories = self._seed_categories()
        self._seed_specializations()
        self._seed_platform_settings()
        self.admin = self._seed_admin()
        self.photographers = self._seed_photographers()
        self.buyers = self._seed_buyers()
        self._seed_services()
        self._seed_availability()
        self._seed_seasonal_demand()
        self._seed_interactions()
        self._seed_bookings()
        self._seed_reviews()
        if not options["skip_history"]:
            self._seed_review_history()
        self._seed_products()
        self._seed_product_files()
        self._seed_product_images()
        self._seed_wallets()
        if not options["skip_analytics"]:
            self._seed_analytics()
        self._refresh_metrics()

        self._summary()

    # ═══════════════════════════════════════════════════════════════════════
    def _flush(self):
        """
        Wipe seeded data.

        TWO SUBTLETIES THIS METHOD EXISTS TO HANDLE:

        1. Most domain models inherit SoftDeleteModel, whose `.delete()`
           deliberately only flips `is_deleted`. A flush that used `.delete()`
           would leave every row in place and then fail on the next PROTECT
           foreign key. We must call `hard_delete()` via `all_objects`.

        2. PROTECT foreign keys make order mandatory. Reviews protect
           bookings, bookings protect services, services protect categories.
           The sequence below walks the dependency graph leaf-first.
        """
        from django.contrib.auth import get_user_model

        from apps.administration.models import (
            ApprovalRequest, AuditLog, ModerationFlag, PlatformSetting,
        )
        from apps.analytics.models import (
            DailyPhotographerStat, PlatformStat, RevenueSnapshot, SearchQueryLog,
        )
        from apps.availability.models import AvailabilityRule, BlackoutDate, TimeSlot
        from apps.bookings.models import Booking
        from apps.catalog.models import Category, Service, ServicePackage, Specialization
        from apps.chat.models import Conversation, Message
        from apps.marketplace.models import (
            CartItem, DigitalProduct, DownloadToken, Order, OrderItem, ProductFile,
        )
        from apps.notifications.models import Broadcast, Notification
        from apps.portfolio.models import (
            PortfolioAlbum, PortfolioImage, PortfolioImageLike, PortfolioVideo,
        )
        from apps.profiles.models import (
            BuyerProfile, PhotographerProfile, TopUpRequest, Wallet, WalletTransaction,
        )
        from apps.recommendations.models import (
            BuyerInteraction, ModelVersion, PhotographerFeature,
            RecommendationEvent, SeasonalDemand,
        )
        from apps.reviews.models import ProductReview, Review, ReviewHelpful
        from apps.wishlist.models import WishlistItem

        User = get_user_model()
        self.stdout.write("  flushing existing data…")

        # Leaf-first order. Anything referenced by a PROTECT FK must appear
        # AFTER whatever references it.
        order = [
            ReviewHelpful, ProductReview, Review,
            DownloadToken, OrderItem, Order, CartItem,
            ProductFile, DigitalProduct,
            RecommendationEvent, PhotographerFeature, BuyerInteraction,
            SeasonalDemand, ModelVersion,
            DailyPhotographerStat, RevenueSnapshot, PlatformStat, SearchQueryLog,
            Message, Conversation,
            Notification, Broadcast,
            WishlistItem,
            PortfolioImageLike, PortfolioImage, PortfolioVideo, PortfolioAlbum,
            TimeSlot, Booking,
            AvailabilityRule, BlackoutDate,
            ServicePackage, Service,
            ApprovalRequest, ModerationFlag, AuditLog,
            WalletTransaction, TopUpRequest, Wallet,
            PhotographerProfile, BuyerProfile,
            Specialization, Category, PlatformSetting,
        ]
        for model in order:
            manager = getattr(model, "all_objects", model.objects)
            qs = manager.all()
            # hard_delete() exists only on SoftDeleteQuerySet.
            (qs.hard_delete if hasattr(qs, "hard_delete") else qs.delete)()

        User.all_objects.exclude(is_superuser=True).hard_delete()
        self.stdout.write(self.style.WARNING("  flushed\n"))

    # ═══════════════════════════════════════════════════════════════════════
    def _seed_categories(self) -> dict:
        from apps.catalog.models import Category

        icons = {
            "wedding": "heart", "corporate": "briefcase", "fashion": "sparkles",
            "birthday": "gift", "graduation": "academic-cap",
        }
        out = {}
        for order, (slug, name) in enumerate(CANONICAL_CATEGORIES):
            cat, _ = Category.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "icon": icons.get(slug, "camera"),
                    "display_order": order,
                    "description": f"{name} photography across Pakistan.",
                    "is_active": True,
                },
            )
            out[name] = cat
        self._ok("categories", len(out))
        return out

    def _seed_specializations(self):
        from apps.catalog.models import Specialization

        count = 0
        for cat_name, names in SPECIALIZATIONS.items():
            for n in names:
                _, created = Specialization.objects.get_or_create(
                    name=n, defaults={"category": self.categories[cat_name]}
                )
                count += int(created)
        self._ok("specializations", Specialization.objects.count())

    def _seed_platform_settings(self):
        """Settings an admin may tune at runtime, without a redeploy."""
        from apps.administration.models import PlatformSetting

        rows = [
            ("booking_expiry_hours", "48", "INT", "Booking expiry (hours)", "bookings"),
            ("booking_min_lead_hours", "24", "INT", "Minimum lead time (hours)", "bookings"),
            ("platform_commission_percent", "10", "FLOAT", "Booking commission %", "money"),
            ("product_commission_percent", "15", "FLOAT", "Marketplace commission %", "money"),
            ("free_cancellation_hours", "48", "INT", "Free cancellation window", "bookings"),
            ("rec_weight_content", "0.55", "FLOAT", "Recommender: content weight", "ai"),
            ("rec_weight_collab", "0.30", "FLOAT", "Recommender: collaborative weight", "ai"),
            ("rec_weight_business", "0.15", "FLOAT", "Recommender: business-rule weight", "ai"),
            ("rec_exploration_slots", "2", "INT", "Guaranteed new-photographer slots", "ai"),
            ("max_pending_bookings", "5", "INT", "Max concurrent pending per buyer", "bookings"),
            ("min_payout_amount", "5000", "FLOAT", "Minimum payout (PKR)", "money"),
        ]
        for key, value, vtype, label, group in rows:
            PlatformSetting.objects.update_or_create(
                key=key,
                defaults={"value": value, "value_type": vtype, "label": label,
                          "group": group, "is_public": group == "ai"},
            )
        self._ok("platform settings", len(rows))

    def _seed_admin(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        admin, created = User.objects.get_or_create(
            email="admin@snapsphere.pk",
            defaults={
                "full_name": "Platform Admin", "role": UserRole.ADMIN,
                "is_staff": True, "is_superuser": True,
                "is_email_verified": True, "city": "Islamabad",
            },
        )
        if created:
            admin.set_password("admin12345")
            admin.save()
        self._ok("admin user", 1, extra="admin@snapsphere.pk / admin12345")
        return admin

    # ═══════════════════════════════════════════════════════════════════════
    def _seed_photographers(self) -> dict:
        """
        Load photographer_profiles.csv (200 rows).

        Column mapping — note the two corrections applied here:
          Price          → base_price × 100, rounded (USD-scale → PKR)
          Response_Time  → avg_response_time_hours, kept as-is; the ML feature
                           pipeline is what inverts it (low = good)
        """
        from django.contrib.auth import get_user_model

        from apps.profiles.services import create_photographer_profile

        User = get_user_model()
        rows = read_csv("photographer_profiles.csv")
        out = {}

        # Capture the CSV's claimed review counts NOW, before any later step
        # recomputes profile.reviews_count from the (still empty) reviews
        # table. Reading them back off the model later is order-dependent and
        # silently halves the generated history.
        self.review_targets = {
            int(r["Photographer_ID"]): int(r["Reviews_Count"]) for r in rows
        }
        # Same reason: the CSV rating is the distribution the generated stars
        # are drawn around, and it must survive later recomputation.
        self.csv_ratings = {
            int(r["Photographer_ID"]): float(r["Avg_Rating"]) for r in rows
        }

        for row in rows:
            pid = int(row["Photographer_ID"])
            first = FIRST_NAMES[pid % len(FIRST_NAMES)]
            last = LAST_NAMES[(pid * 7) % len(LAST_NAMES)]
            name = f"{first} {last}"
            city, lat, lng = PAKISTAN_CITIES[pid % len(PAKISTAN_CITIES)]

            user, created = User.objects.get_or_create(
                email=f"photographer{pid}@snapsphere.pk",
                defaults={
                    "full_name": name,
                    "role": UserRole.PHOTOGRAPHER,
                    "city": city,
                    "latitude": Decimal(f"{lat + random.uniform(-0.05, 0.05):.6f}"),
                    "longitude": Decimal(f"{lng + random.uniform(-0.05, 0.05):.6f}"),
                    "phone": f"03{random.randint(100000000, 499999999)}",
                    "is_email_verified": True,
                },
            )
            if created:
                user.set_password("photographer123")
                user.save(update_fields=["password"])

            profile = create_photographer_profile(user)
            category = self.categories[row["Event_Type"]]
            rating = Decimal(row["Avg_Rating"])
            reviews = int(row["Reviews_Count"])

            profile.business_name = f"{name} Photography"
            profile.tagline = f"{row['Event_Type']} specialist in {city}"
            profile.bio = (
                f"{name} is a {row['Event_Type'].lower()} photographer based in "
                f"{city} with {row['Years_Experience']} years of professional "
                f"experience. Known for a clean, natural style and reliable "
                f"delivery, {first} has completed hundreds of shoots across "
                f"Pakistan and works with couples, families and brands who want "
                f"images that still feel honest ten years later."
            )
            profile.years_experience = int(row["Years_Experience"])
            profile.base_price = to_pkr(row["Price"])
            profile.avg_rating = rating
            profile.reviews_count = reviews
            profile.bayesian_rating = profile.recompute_bayesian()
            profile.success_rate = Decimal(row["Bookings_Success_Rate"])
            profile.avg_response_time_hours = Decimal(row["Response_Time"])
            profile.portfolio_score = int(row["Portfolio_Score"])
            profile.profile_views = reviews * random.randint(8, 25)
            # 85% approved: the rest populate the admin approval queue so that
            # screen has something real to show.
            profile.is_approved = random.random() < 0.85
            profile.approved_at = timezone.now() if profile.is_approved else None
            profile.approved_by = self.admin if profile.is_approved else None
            profile.is_verified = rating >= Decimal("4.5") and reviews > 150
            profile.is_featured = rating >= Decimal("4.7") and reviews > 300
            profile.save()

            profile.categories.set([category])
            specs = SPECIALIZATIONS[row["Event_Type"]]
            from apps.catalog.models import Specialization

            profile.specializations.set(
                Specialization.objects.filter(name__in=random.sample(specs, 2))
            )
            out[pid] = profile

        self._ok("photographers", len(out))
        return out

    def _seed_buyers(self) -> dict:
        """Create a user for every distinct Buyer_ID in buyer_interactions.csv."""
        from django.contrib.auth import get_user_model

        from apps.profiles.services import create_buyer_profile

        User = get_user_model()
        rows = read_csv("buyer_interactions.csv")
        buyer_ids = sorted({int(r["Buyer_ID"]) for r in rows})
        out = {}

        for bid in buyer_ids:
            first = FIRST_NAMES[(bid * 3) % len(FIRST_NAMES)]
            last = LAST_NAMES[(bid * 11) % len(LAST_NAMES)]
            city, lat, lng = PAKISTAN_CITIES[bid % len(PAKISTAN_CITIES)]

            user, created = User.objects.get_or_create(
                email=f"buyer{bid}@snapsphere.pk",
                defaults={
                    "full_name": f"{first} {last}",
                    "role": UserRole.BUYER,
                    "city": city,
                    "latitude": Decimal(f"{lat + random.uniform(-0.05, 0.05):.6f}"),
                    "longitude": Decimal(f"{lng + random.uniform(-0.05, 0.05):.6f}"),
                    "phone": f"03{random.randint(100000000, 499999999)}",
                    "is_email_verified": True,
                },
            )
            if created:
                user.set_password("buyer12345")
                user.save(update_fields=["password"])
            create_buyer_profile(user)
            out[bid] = user

        self._ok("buyers", len(out))
        return out

    def _seed_services(self):
        """Give every photographer three tiers around their base price."""
        from apps.catalog.models import Service

        tiers = [
            ("Essential {cat} Package", 0.7, 3, 40),
            ("Signature {cat} Package", 1.0, 6, 90),
            ("Premium {cat} Package", 1.6, 10, 180),
        ]
        created = 0
        for profile in self.photographers.values():
            if profile.services.exists():
                continue
            category = profile.categories.first()
            for order, (title, mult, hours, photos) in enumerate(tiers):
                Service.objects.create(
                    photographer=profile,
                    category=category,
                    title=title.format(cat=category.name),
                    description=(
                        f"{hours} hours of {category.name.lower()} coverage with "
                        f"{photos} professionally edited photographs, delivered "
                        f"through a private online gallery."
                    ),
                    price=(profile.base_price * Decimal(str(mult))).quantize(Decimal("1")),
                    duration_hours=hours,
                    edited_photos_count=photos,
                    delivery_days=14 if order < 2 else 21,
                    includes=[
                        f"{hours} hours coverage",
                        f"{photos} edited photos",
                        "Private online gallery",
                        "Print release",
                    ] + (["Second photographer", "Same-day previews"] if order == 2 else []),
                    display_order=order,
                    is_active=True,
                )
                created += 1
        self._ok("services", created)

    def _seed_availability(self):
        """Default rules are created with each profile; add some blackouts."""
        from apps.availability.models import BlackoutDate

        rows = []
        today = timezone.localdate()
        for profile in list(self.photographers.values())[:80]:
            start = today + timedelta(days=random.randint(5, 90))
            rows.append(
                BlackoutDate(
                    photographer=profile,
                    start_date=start,
                    end_date=start + timedelta(days=random.randint(1, 5)),
                    reason=random.choice(
                        ["Travelling", "Personal leave", "Equipment servicing",
                         "Destination shoot", "Family event"]
                    ),
                )
            )
        BlackoutDate.objects.bulk_create(rows, ignore_conflicts=True)
        self._ok("blackout dates", len(rows))

    def _seed_seasonal_demand(self):
        """Load seasonal_demand.csv — 12 months × 5 categories."""
        from apps.recommendations.models import SeasonalDemand

        months = {
            "January": 1, "February": 2, "March": 3, "April": 4, "May": 5,
            "June": 6, "July": 7, "August": 8, "September": 9, "October": 10,
            "November": 11, "December": 12,
        }
        count = 0
        for row in read_csv("seasonal_demand.csv"):
            SeasonalDemand.objects.update_or_create(
                month=months[row["Month"]],
                category=self.categories[row["Event_Type"]],
                defaults={
                    "avg_bookings": int(row["Avg_Bookings"]),
                    "avg_price": to_pkr(row["Avg_Price"]),
                    "demand_score": int(row["Demand_Score"]),
                },
            )
            count += 1
        self._ok("seasonal demand rows", count)

    def _seed_interactions(self):
        """
        Load buyer_interactions.csv — the collaborative-filtering training set.

        One CSV row expands into several typed interactions, because the raw
        row records a whole session (viewed, clicked N times, interacted with
        the portfolio, maybe enquired) and the CF matrix needs each signal
        weighted separately.
        """
        from apps.recommendations.models import BuyerInteraction, BuyerInteractionType

        rows = read_csv("buyer_interactions.csv")
        objects = []
        for row in rows:
            buyer = self.buyers.get(int(row["Buyer_ID"]))
            photographer = self.photographers.get(int(row["Photographer_ID"]))
            if not buyer or not photographer:
                continue
            category = self.categories.get(row["Search_Keyword"])
            ts = timezone.make_aware(
                datetime.strptime(row["Timestamp"], "%Y-%m-%d")
            )

            def add(kind):
                objects.append(
                    BuyerInteraction(
                        buyer=buyer, photographer=photographer,
                        interaction_type=kind,
                        search_keyword=row["Search_Keyword"],
                        category=category, created_at=ts,
                    )
                )

            add(BuyerInteractionType.SEARCH)
            if row["Profile_View"] == "Yes":
                add(BuyerInteractionType.VIEW)
            if int(row["Clicks"]) > 0:
                add(BuyerInteractionType.CLICK)
            if int(row["Portfolio_Interactions"]) > 0:
                add(BuyerInteractionType.PORTFOLIO)
            if row["Inquiry_Made"] == "Yes":
                add(BuyerInteractionType.INQUIRY)
            if row["Booking_Status"] == "Booked":
                add(BuyerInteractionType.COMPLETED)
            elif row["Booking_Status"] == "Pending":
                add(BuyerInteractionType.BOOKING)

        for obj in objects:
            from apps.recommendations.models import INTERACTION_WEIGHTS

            obj.weight = INTERACTION_WEIGHTS.get(obj.interaction_type, 1.0)
        BuyerInteraction.objects.bulk_create(objects, batch_size=500)
        self._ok("buyer interactions", len(objects))

    # ═══════════════════════════════════════════════════════════════════════
    def _seed_bookings(self):
        """
        Derive bookings from buyer_interactions.csv outcomes.

            Booked    → COMPLETED  (reviewable)
            Pending   → PENDING    (sits in the photographer's inbox)
            Cancelled → CANCELLED

        Slot assignment is deliberately spread out: the uniq_active_booking_slot
        index would otherwise reject two PENDING rows landing on the same
        photographer/date/time, which is exactly the guard working as intended.
        """
        from apps.bookings.constants import BookingStatus, PaymentMethod, PaymentStatus
        from apps.bookings.models import Booking, BookingPayment, BookingStatusHistory

        status_map = {
            "Booked": BookingStatus.COMPLETED,
            "Pending": BookingStatus.PENDING,
            "Cancelled": BookingStatus.CANCELLED,
        }
        rows = read_csv("buyer_interactions.csv")
        taken: set[tuple] = set()
        made = 0
        today = timezone.localdate()

        for row in rows:
            buyer = self.buyers.get(int(row["Buyer_ID"]))
            profile = self.photographers.get(int(row["Photographer_ID"]))
            if not buyer or not profile:
                continue
            service = profile.services.order_by("?").first()
            if not service:
                continue

            status = status_map[row["Booking_Status"]]
            if status == BookingStatus.PENDING:
                event_date = today + timedelta(days=random.randint(3, 60))
            else:
                event_date = datetime.strptime(row["Timestamp"], "%Y-%m-%d").date()

            start = time(random.choice([9, 10, 11, 14, 15, 16]), 0)
            key = (profile.pk, event_date, start)
            if status in (BookingStatus.PENDING,) and key in taken:
                continue
            taken.add(key)

            created_at = timezone.make_aware(
                datetime.combine(
                    event_date - timedelta(days=random.randint(7, 45)),
                    time(random.randint(9, 20), random.randint(0, 59)),
                )
            )
            city = buyer.city
            booking = Booking(
                buyer=buyer,
                photographer=profile,
                service=service,
                category=service.category,
                event_date=event_date,
                start_time=start,
                end_time=time(min(start.hour + service.duration_hours, 23), 0),
                duration_hours=service.duration_hours,
                location_address=f"{random.randint(1, 400)} Main Boulevard, {city}",
                location_city=city,
                location_latitude=buyer.latitude,
                location_longitude=buyer.longitude,
                unit_price=service.price,
                quantity=1,
                travel_fee=Decimal(random.choice([0, 0, 0, 2000, 3500])),
                commission_percent=Decimal("10.00"),
                status=status,
                guest_count=random.choice([None, 50, 120, 250, 400]),
                notes=random.choice(
                    ["", "Please arrive 30 minutes early for setup.",
                     "Outdoor shoot — bring backup lighting.",
                     "Family of 12, need group shots."]
                ),
                expires_at=created_at + timedelta(hours=48),
            )
            booking.calculate_totals()

            if status == BookingStatus.COMPLETED:
                booking.responded_at = created_at + timedelta(
                    hours=float(profile.avg_response_time_hours)
                )
                booking.accepted_at = booking.responded_at
                booking.completed_at = timezone.make_aware(
                    datetime.combine(event_date + timedelta(days=1), time(12, 0))
                )
                booking.photographer_marked_complete = True
                booking.buyer_confirmed_completion = True
            elif status == BookingStatus.CANCELLED:
                booking.cancelled_at = created_at + timedelta(days=1)
                booking.cancelled_by = buyer
                booking.cancellation_reason = random.choice(
                    ["BUYER_CHANGED_PLANS", "EVENT_CANCELLED", "PRICE_DISAGREEMENT"]
                )

            booking.save()
            Booking.objects.filter(pk=booking.pk).update(created_at=created_at)
            made += 1

            BookingStatusHistory.objects.create(
                booking=booking, from_status="", to_status=BookingStatus.PENDING,
                changed_by=buyer, actor_role="BUYER", note="Booking requested",
            )
            if status != BookingStatus.PENDING:
                BookingStatusHistory.objects.create(
                    booking=booking, from_status=BookingStatus.PENDING,
                    to_status=status, changed_by=profile.user,
                    actor_role="PHOTOGRAPHER",
                )

            BookingPayment.objects.create(
                booking=booking,
                method=random.choice(
                    [PaymentMethod.CASH, PaymentMethod.BANK_TRANSFER,
                     PaymentMethod.EASYPAISA]
                ),
                status=(
                    PaymentStatus.FULLY_PAID
                    if status == BookingStatus.COMPLETED
                    else PaymentStatus.UNPAID
                ),
                paid_amount=(
                    booking.total_price
                    if status == BookingStatus.COMPLETED
                    else Decimal("0.00")
                ),
                is_verified=status == BookingStatus.COMPLETED,
            )

        self._ok("bookings", made)

    def _load_yelp_by_star(self, limit: int = 40000) -> dict[int, list[str]]:
        """Bucket real review prose by star rating so tone matches the score."""
        buckets: dict[int, list[str]] = {1: [], 2: [], 3: [], 4: [], 5: []}
        with (RAW / "yelp.csv").open(encoding="utf-8", errors="ignore") as fh:
            for i, row in enumerate(csv.DictReader(fh)):
                if i > limit:
                    break
                try:
                    stars = int(row["stars"])
                except (ValueError, KeyError):
                    continue
                text = (row.get("text") or "").strip().replace("\n", " ")
                if 60 <= len(text) <= 420 and stars in buckets:
                    buckets[stars].append(text)
        return buckets

    def _seed_review_history(self):
        """
        Generate the booking + review history behind each photographer's
        headline rating.

        WHY THIS EXISTS
        ---------------
        photographer_profiles.csv carries Avg_Rating and Reviews_Count as
        pre-existing facts (up to 499 reviews). Seeding those numbers onto the
        profile without creating the underlying rows produces a profile that
        claims "4.95 from 432 reviews" above an empty review list and a
        rating histogram of all zeros — visibly broken, and it makes the
        review endpoints untestable.

        So the history is materialised: one completed booking and one review
        per claimed review, dated across the past three years, with prose
        drawn from yelp.csv bucketed to match the star rating.

        The active-slot unique index does not apply here — its generated
        column is NULL for anything that is not PENDING or ACCEPTED — so
        historical COMPLETED bookings can share dates freely.
        """
        from django.db.models import Count

        from apps.bookings.constants import BookingStatus
        from apps.bookings.models import Booking
        from apps.reviews.models import Review

        buyers = list(self.buyers.values())
        today = timezone.localdate()

        total_bookings = 0
        total_reviews = 0

        # How many reviews already exist per photographer, in ONE query.
        # `profile.reviews_count` cannot be used here: for photographers that
        # _seed_reviews() touched it holds the recomputed value, and for the
        # rest it still holds the CSV value — so subtracting it yields either
        # the right answer or zero, depending on an ordering coincidence.
        # Counting the actual rows is correct regardless of step order.
        existing_counts = dict(
            Review.objects.values_list("photographer_id")
            .annotate(n=Count("id"))
            .values_list("photographer_id", "n")
        )

        for pid, profile in self.photographers.items():
            target = self.review_targets.get(pid, 0) - existing_counts.get(profile.pk, 0)
            if target <= 0:
                continue

            services = list(profile.services.all())
            if not services:
                continue

            mean_rating = float(self.csv_ratings.get(pid, profile.avg_rating or 4.0))
            category = profile.categories.first()
            category_name = category.name if category else None

            # ─── 1. Historical completed bookings ────────────────────────────
            pending_bookings = []
            for _ in range(target):
                buyer = random.choice(buyers)
                service = random.choice(services)
                days_ago = random.randint(30, 1095)  # up to 3 years back
                event_date = today - timedelta(days=days_ago)
                created = timezone.make_aware(
                    datetime.combine(
                        event_date - timedelta(days=random.randint(7, 40)),
                        time(random.randint(9, 20), random.randint(0, 59)),
                    )
                )
                booking = Booking(
                    buyer=buyer,
                    photographer=profile,
                    service=service,
                    category=service.category or category,
                    event_date=event_date,
                    start_time=time(random.choice([9, 10, 11, 14, 15, 16]), 0),
                    duration_hours=service.duration_hours,
                    location_address=f"{random.randint(1, 400)} Main Boulevard, {buyer.city}",
                    location_city=buyer.city,
                    unit_price=service.price,
                    quantity=1,
                    commission_percent=Decimal("10.00"),
                    status=BookingStatus.COMPLETED,
                    expires_at=created + timedelta(hours=48),
                    responded_at=created + timedelta(hours=random.randint(1, 24)),
                    accepted_at=created + timedelta(hours=random.randint(1, 24)),
                    completed_at=timezone.make_aware(
                        datetime.combine(event_date + timedelta(days=1), time(12, 0))
                    ),
                    photographer_marked_complete=True,
                    buyer_confirmed_completion=True,
                    has_review=True,
                )
                booking.calculate_totals()
                pending_bookings.append(booking)

            Booking.objects.bulk_create(pending_bookings, batch_size=500)
            total_bookings += len(pending_bookings)

            # MySQL does not return primary keys from a bulk insert, so the
            # rows are re-read to attach reviews to them.
            booking_ids = list(
                Booking.objects.filter(
                    photographer=profile,
                    status=BookingStatus.COMPLETED,
                    has_review=True,
                )
                .exclude(review__isnull=False)
                .values_list("pk", "buyer_id")[:target]
            )

            # `created_at` is auto_now_add, and Django's pre_save overrides
            # any value we set — including through bulk_create. So every
            # historical booking lands with created_at = now, while
            # responded_at sits years in the past. The response-time metric is
            # (responded_at - created_at), which then comes out large and
            # NEGATIVE and overflows DECIMAL(6,2).
            #
            # Back-dating it here in one UPDATE keeps the timeline coherent:
            # requested a few hours before the photographer responded.
            Booking.objects.filter(
                pk__in=[pk for pk, _ in booking_ids]
            ).update(created_at=F("responded_at") - timedelta(hours=6))

            # ─── 2. Reviews ──────────────────────────────────────────────────
            reviews = []
            for booking_pk, buyer_id in booking_ids:
                # Draw stars around the photographer's headline rating so the
                # recomputed average lands close to the CSV value.
                stars = max(1, min(5, int(round(random.gauss(mean_rating, 0.55)))))
                reviews.append(
                    Review(
                        booking_id=booking_pk,
                        buyer_id=buyer_id,
                        photographer=profile,
                        rating=stars,
                        rating_quality=max(1, min(5, stars + random.choice([-1, 0, 0, 1]))),
                        rating_professionalism=max(1, min(5, stars + random.choice([0, 0, 1]))),
                        rating_communication=max(1, min(5, stars + random.choice([-1, 0, 1]))),
                        rating_value=max(1, min(5, stars + random.choice([-1, 0, 0]))),
                        rating_punctuality=max(1, min(5, stars + random.choice([0, 0, 1]))),
                        title=review_title(stars),
                        comment=review_text(stars, category_name),
                        helpful_count=random.randint(0, 40),
                    )
                )
            Review.objects.bulk_create(reviews, batch_size=500)
            total_reviews += len(reviews)

        self._ok("historical bookings", total_bookings)
        self._ok("historical reviews", total_reviews, extra="photography prose")

    def _seed_reviews(self):
        """
        Write reviews for the bookings derived from buyer_interactions.csv.

        WHERE THE REVIEW TEXT COMES FROM — AND WHY NOT FROM THE CSVs
        ------------------------------------------------------------
        reviews_feedback.csv is unusable: 5 distinct sentences across 300 rows,
        with randomly assigned Sentiment labels (run
        `python -m ml.pipelines.ingest --audit` for the evidence).

        yelp.csv IS used — but only to TRAIN the sentiment classifier, where
        44,610 human-written reviews with trustworthy star labels are exactly
        what is needed. It is not used for display: its reviews are about
        restaurants, so seeded profiles ended up showing "one of the best
        dining experiences we had in Phoenix" under a wedding portfolio.

        Display prose is generated by apps.core.review_text instead —
        photography-domain templates, tone-matched to the star rating.
        """
        from apps.bookings.constants import BookingStatus
        from apps.bookings.models import Booking
        from apps.profiles.services import refresh_photographer_rating
        from apps.reviews.models import Review

        completed = list(
            Booking.objects.filter(status=BookingStatus.COMPLETED).select_related(
                "photographer", "buyer"
            )
        )
        made = 0
        touched = set()

        for booking in completed:
            # 72% of completed bookings get reviewed — a realistic response rate.
            if random.random() > 0.72:
                continue
            base = float(booking.photographer.avg_rating)
            stars = max(1, min(5, int(round(random.gauss(base, 0.7)))))

            Review.objects.create(
                booking=booking,
                buyer=booking.buyer,
                photographer=booking.photographer,
                rating=stars,
                rating_quality=max(1, min(5, stars + random.choice([-1, 0, 0, 1]))),
                rating_professionalism=max(1, min(5, stars + random.choice([0, 0, 1]))),
                rating_communication=max(1, min(5, stars + random.choice([-1, 0, 1]))),
                rating_value=max(1, min(5, stars + random.choice([-1, 0, 0]))),
                rating_punctuality=max(1, min(5, stars + random.choice([0, 0, 1]))),
                title=review_title(stars),
                comment=review_text(
                    stars,
                    booking.category.name if booking.category else None,
                ),
                helpful_count=random.randint(0, 24),
            )
            Booking.objects.filter(pk=booking.pk).update(has_review=True)
            touched.add(booking.photographer_id)
            made += 1

        for profile in self.photographers.values():
            if profile.pk in touched:
                refresh_photographer_rating(profile)

        self._ok("reviews", made, extra="photography prose, tone-matched to rating")

    def _seed_products(self):
        """Digital marketplace listings, priced from data.csv-like ranges."""
        from apps.marketplace.models import DigitalProduct, ProductType

        templates = [
            (ProductType.LIGHTROOM_PRESET, "Warm Desi Wedding Presets", 1500, 4500),
            (ProductType.LIGHTROOM_PRESET, "Moody Film Preset Pack", 1200, 3800),
            (ProductType.WEDDING_LUT, "Cinematic Wedding LUT Bundle", 2500, 6500),
            (ProductType.PHOTOSHOP_TEMPLATE, "Editorial Retouch Actions", 1800, 5200),
            (ProductType.ALBUM_TEMPLATE, "Luxury Album Layout Set", 3000, 8500),
            (ProductType.VIDEO_EFFECT, "Highlight Reel Transitions", 2200, 6000),
            (ProductType.STOCK_PHOTO, "Lahore Architecture Stock Pack", 900, 3200),
            (ProductType.OVERLAY, "Golden Hour Light Overlays", 1100, 3400),
        ]
        sellers = [p for p in self.photographers.values() if p.is_approved][:60]
        made = 0
        for seller in sellers:
            for ptype, name, lo, hi in random.sample(templates, random.randint(1, 3)):
                price = Decimal(str(random.randrange(lo, hi, 100)))
                DigitalProduct.objects.create(
                    seller=seller,
                    category=seller.categories.first(),
                    title=f"{name} — {seller.user.first_name_only} Edition",
                    description=(
                        f"A professionally crafted {ptype.label.lower()} set built "
                        f"from {seller.years_experience} years of real client work. "
                        f"Drag-and-drop ready, tested on Pakistani skin tones and "
                        f"South Asian wedding lighting."
                    ),
                    product_type=ptype,
                    price=price,
                    compare_at_price=price * Decimal("1.5"),
                    is_published=True,
                    is_approved=random.random() < 0.9,
                    published_at=timezone.now() - timedelta(days=random.randint(1, 300)),
                    sales_count=random.randint(0, 180),
                    view_count=random.randint(50, 4000),
                    file_count=random.randint(1, 40),
                    total_size_mb=Decimal(str(round(random.uniform(2, 480), 2))),
                    compatible_with=["Lightroom Classic 12+", "Lightroom Mobile"],
                    tags=[ptype.label, seller.categories.first().name],
                )
                made += 1
        self._ok("digital products", made)

    def _seed_product_files(self):
        """
        Give every product something to actually download.

        WHY THIS EXISTS
        ---------------
        `_seed_products` set `file_count` to a plausible number but created no
        `ProductFile` rows, so the entire download flow — token, redemption,
        streaming, the `max_downloads` cap — had nothing to operate on and
        could not be demonstrated or tested end to end.

        The files are small text stand-ins, not real presets. That is the
        honest choice: shipping fabricated .xmp binaries would look like real
        product data in a demo. Each one names itself for what it is.

        They are written through `ProductFile.file`, which is bound to
        `private_storage`, so they land in PRIVATE_MEDIA_ROOT and are
        unreachable by URL — which is the property the download token exists
        to enforce.
        """
        from django.core.files.base import ContentFile

        from apps.marketplace.models import DigitalProduct, ProductFile

        products = DigitalProduct.objects.filter(is_published=True)
        made = 0
        for product in products.iterator():
            if product.files.exists():
                continue

            count = min(product.file_count or 1, 3)
            total = Decimal("0.00")
            for index in range(count):
                size = Decimal(str(round(random.uniform(0.4, 12.0), 2)))
                name = f"{slugify(product.title)[:40]}-{index + 1}.xmp"
                body = (
                    f"# SnapSphere sample asset\n"
                    f"# Product: {product.title}\n"
                    f"# File {index + 1} of {count}\n"
                    f"# This is seeded placeholder content, not a real preset.\n"
                )
                product_file = ProductFile(
                    product=product,
                    name=name,
                    file_size_mb=size,
                    display_order=index,
                )
                product_file.file.save(name, ContentFile(body.encode()), save=False)
                product_file.save()
                total += size
                made += 1

            # Keep the advertised metadata honest about what is really there.
            DigitalProduct.objects.filter(pk=product.pk).update(
                file_count=count, total_size_mb=total
            )
        self._ok("product files", made, "in private_media")

    def _seed_product_images(self):
        """
        Cover art for every product, generated deterministically.

        WHY THIS EXISTS
        ---------------
        No image was ever seeded anywhere in this project: all 124 products had
        a blank `thumbnail`, so the Shop grid rendered a grey placeholder icon
        on every card and looked broken rather than empty.

        WHY GENERATED AND NOT DOWNLOADED
        --------------------------------
        These products are colour-grading presets and LUTs, and what a preset
        listing actually shows IS a colour swatch — so a generated gradient is
        an honest representation of the product, not a stand-in for a
        photograph the platform does not have. Downloading real photos would
        put someone else's copyrighted work in the demo, which is exactly what
        `DigitalProduct.is_approved` exists to prevent.

        The palette is derived from a hash of the title, so a given product
        always gets the same art across reseeds — a random one would make
        every screenshot in the report look like a different app.
        """
        from io import BytesIO

        from django.core.files.base import ContentFile
        from PIL import Image, ImageDraw, ImageFont

        from apps.marketplace.models import DigitalProduct

        # Warm golds through to cool blues — the app's own palette, so the
        # shop grid reads as one product rather than a bag of stock images.
        PALETTES = [
            ((212, 168, 67), (61, 42, 16)),
            ((74, 143, 212), (30, 58, 88)),
            ((61, 184, 122), (26, 61, 46)),
            ((224, 90, 90), (61, 26, 26)),
            ((224, 151, 58), (61, 42, 16)),
            ((150, 110, 200), (48, 34, 66)),
            ((90, 180, 200), (28, 56, 62)),
            ((200, 120, 160), (62, 34, 48)),
        ]
        WIDTH, HEIGHT = 800, 560

        def font(size: int):
            try:
                return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
            except OSError:
                # load_default(size=) needs Pillow >= 10.1; the bare call is
                # the floor and still renders, just small.
                try:
                    return ImageFont.load_default(size=size)
                except TypeError:
                    return ImageFont.load_default()

        def render(product, variant: int) -> bytes:
            seed = sum(ord(c) for c in product.title) + variant
            top, bottom = PALETTES[seed % len(PALETTES)]

            image = Image.new("RGB", (WIDTH, HEIGHT))
            draw = ImageDraw.Draw(image)

            # Vertical gradient, drawn a row at a time.
            for y in range(HEIGHT):
                ratio = y / HEIGHT
                draw.line(
                    [(0, y), (WIDTH, y)],
                    fill=tuple(
                        int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)
                    ),
                )

            # A couple of translucent discs so the swatch has some depth
            # instead of reading as a flat colour chip.
            overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
            odraw = ImageDraw.Draw(overlay)
            for index in range(3):
                radius = 150 + ((seed + index * 47) % 180)
                cx = (seed * (index + 3) * 53) % WIDTH
                cy = (seed * (index + 5) * 31) % HEIGHT
                odraw.ellipse(
                    [cx - radius, cy - radius, cx + radius, cy + radius],
                    fill=(255, 255, 255, 14 + index * 6),
                )
            image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

            draw = ImageDraw.Draw(image)
            if variant == 0:
                # The grid thumbnail renders about 170pt wide and the card
                # already prints the title underneath it. Burning the title in
                # as well duplicates it and turns to mush at that size, so the
                # thumbnail carries only the product type.
                draw.text(
                    (48, HEIGHT - 96),
                    product.get_product_type_display().upper(),
                    font=font(40),
                    fill=(255, 255, 255),
                )
            else:
                # Detail-screen previews are shown large, where a title reads.
                draw.text(
                    (48, HEIGHT - 132),
                    product.get_product_type_display().upper(),
                    font=font(26),
                    fill=(255, 255, 255),
                )
                title = product.title.split(" — ")[0]
                draw.text(
                    (48, HEIGHT - 96), title[:26], font=font(44), fill=(255, 255, 255)
                )

            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=82)
            return buffer.getvalue()

        thumbs = previews = 0
        for product in DigitalProduct.objects.iterator():
            if not product.thumbnail:
                product.thumbnail.save(
                    f"{slugify(product.title)[:50]}.jpg",
                    ContentFile(render(product, 0)),
                    save=False,
                )
                thumbs += 1

            if not product.preview_images:
                paths = []
                for variant in range(1, 4):
                    name = f"products/previews/{slugify(product.title)[:44]}-{variant}.jpg"
                    path = Path(settings.MEDIA_ROOT) / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(render(product, variant))
                    # preview_images stores storage-relative paths, not URLs —
                    # the serializer resolves them against MEDIA_URL.
                    paths.append(name)
                product.preview_images = paths
                previews += len(paths)

            product.save(update_fields=["thumbnail", "preview_images"])

        self._ok("product thumbnails", thumbs)
        self._ok("product previews", previews)

    def _seed_wallets(self):
        """
        Opening balances for the test accounts, written through the ledger.

        `credit_wallet` is used rather than a direct `balance = X` write, so
        every seeded rupee has a matching `WalletTransaction` with
        balance_before and balance_after. A seeded balance with no ledger row
        would break the invariant the ledger exists to prove, and the first
        person to reconcile the two would be chasing a bug that was never in
        the application.

        No TopUpRequest is created: those need a receipt image, and inventing
        a fake bank receipt is exactly the kind of fabricated record this
        project should not ship.
        """
        from apps.profiles.models import WalletTransactionType
        from apps.profiles.services import credit_wallet

        credited = 0
        for user in list(self.buyers.values())[:40]:
            amount = Decimal(str(random.randrange(15_000, 90_000, 5_000)))
            credit_wallet(
                user,
                amount,
                txn_type=WalletTransactionType.TOPUP,
                reference="SEED",
                description="Seeded opening balance (demo data)",
            )
            credited += 1
        self._ok("wallets credited", credited, "via the ledger")

    def _seed_analytics(self):
        """
        Load the four service_*.csv files into daily_photographer_stats.

        The files have inconsistent schemas — service_monitoring.csv is missing
        Portfolio_Interactions, and IDs appear both as "P001" and as bare
        integers. Both are normalised here rather than in the model, so the
        table stays clean.
        """
        from apps.analytics.models import DailyPhotographerStat

        files = [
            "service_engagement_dataset.csv",
            "service_revenue_dataset.csv",
            "service_general_dataset.csv",
            "service_monitoring_dataset.csv",
            "service_monitoring.csv",
        ]
        rows_out, seen = [], set()

        for fname in files:
            try:
                rows = read_csv(fname)
            except FileNotFoundError:
                continue
            for row in rows:
                raw_id = row["Photographer_ID"]
                pid = int(raw_id[1:]) if raw_id.startswith("P") else int(raw_id)
                profile = self.photographers.get(pid)
                if not profile:
                    continue
                try:
                    d = datetime.strptime(row["Date"], "%Y-%m-%d").date()
                except ValueError:
                    continue
                key = (profile.pk, d)
                if key in seen:
                    continue
                seen.add(key)

                rows_out.append(
                    DailyPhotographerStat(
                        photographer=profile,
                        date=d,
                        category=self.categories.get(row.get("Event_Type", "")),
                        search_visibility=int(row.get("Search_Visibility", 0) or 0),
                        profile_views=int(row.get("Profile_Views", 0) or 0),
                        clicks=int(row.get("Clicks", 0) or 0),
                        # Missing in service_monitoring.csv → default 0.
                        portfolio_interactions=int(row.get("Portfolio_Interactions", 0) or 0),
                        bookings_created=int(row.get("Bookings", 0) or 0),
                        bookings_completed=int(row.get("Bookings", 0) or 0),
                        revenue=to_pkr(row.get("Revenue", 0) or 0),
                        conversion_rate=float(row.get("Conversion_Rate", 0) or 0),
                        response_rate=float(row.get("Response_Rate", 0) or 0),
                    )
                )

        DailyPhotographerStat.objects.bulk_create(
            rows_out, batch_size=500, ignore_conflicts=True
        )
        self._ok("daily analytics rows", len(rows_out), extra=f"from {len(files)} CSVs")

    def _refresh_metrics(self):
        """
        Recompute every denormalised metric from the rows that now exist.

        This runs LAST and is the step that makes the profile self-consistent:
        `avg_rating`, `reviews_count` and `bayesian_rating` are derived from
        the reviews table rather than copied from the CSV, so the headline
        number on a profile always matches the reviews listed underneath it.

        It is the same code path the nightly Celery job uses, so the seeded
        database is in exactly the state the running platform maintains.
        """
        from apps.catalog.models import Category
        from apps.profiles.services import (
            refresh_photographer_booking_metrics,
            refresh_photographer_rating,
        )

        for profile in self.photographers.values():
            refresh_photographer_rating(profile)
            refresh_photographer_booking_metrics(profile)

        for cat in Category.objects.all():
            cat.photographer_count = cat.photographers.filter(is_approved=True).count()
            cat.booking_count = cat.bookings.count()
            cat.save(update_fields=["photographer_count", "booking_count"])

        self._ok("metrics refreshed", len(self.photographers))

    # ═══════════════════════════════════════════════════════════════════════
    def _ok(self, label: str, count: int, extra: str = ""):
        suffix = f"  ({extra})" if extra else ""
        self.stdout.write(
            self.style.SUCCESS(f"  [OK] {label:<26} {count:>6}{suffix}")
        )

    def _summary(self):
        from django.contrib.auth import get_user_model

        from apps.bookings.models import Booking
        from apps.catalog.models import Service
        from apps.marketplace.models import DigitalProduct
        from apps.recommendations.models import BuyerInteraction
        from apps.reviews.models import Review

        User = get_user_model()
        self.stdout.write(self.style.MIGRATE_HEADING("\nSeed complete\n"))
        self.stdout.write(
            f"  users        {User.objects.count():>6}   "
            f"(buyers {User.objects.buyers().count()}, "
            f"photographers {User.objects.photographers().count()})"
        )
        self.stdout.write(f"  services     {Service.objects.count():>6}")
        self.stdout.write(f"  bookings     {Booking.objects.count():>6}")
        self.stdout.write(f"  reviews      {Review.objects.count():>6}")
        self.stdout.write(f"  products     {DigitalProduct.objects.count():>6}")
        self.stdout.write(f"  interactions {BuyerInteraction.objects.count():>6}")
        self.stdout.write(
            self.style.WARNING(
                "\n  Logins:  admin@snapsphere.pk / admin12345"
                "\n           photographer1@snapsphere.pk / photographer123"
                "\n           buyer1@snapsphere.pk / buyer12345\n"
            )
        )
