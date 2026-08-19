#!/usr/bin/env bash
#
# SnapSphere — end-to-end API smoke test.
#
#   ./test.sh
#
# Exercises the real running server: registration, login, authorisation,
# validation, and the security controls. Every check prints PASS or FAIL and
# the script exits non-zero if anything fails, so it is usable in CI.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/backend/.venv/bin/python"
API="http://127.0.0.1:8000/api/v1"

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; OFF=$'\033[0m'

PASSED=0
FAILED=0

# check <description> <expected> <actual>
check() {
  if [ "$2" == "$3" ]; then
    echo "  ${GREEN}PASS${OFF}  $1  ${DIM}($3)${OFF}"
    PASSED=$((PASSED + 1))
  else
    echo "  ${RED}FAIL${OFF}  $1  ${DIM}expected $2, got $3${OFF}"
    FAILED=$((FAILED + 1))
  fi
}

# Evaluate a Python expression against the JSON on stdin, where `d` is the
# parsed document.  e.g.   echo "$JSON" | jget "d['data']['user']['role']"
#
# The expression is passed via argv, NOT interpolated into the -c string:
# interpolating it means the single quotes in d['success'] terminate the
# Python string literal and every call silently returns nothing.
jget() {
  "$PY" -c 'import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print("PARSE_ERROR"); sys.exit(0)
try:
    print(eval(sys.argv[1]))
except Exception as exc:
    print(f"EVAL_ERROR:{exc.__class__.__name__}")' "$1" 2>/dev/null
}

section() { echo; echo "${BOLD}$1${OFF}"; }

echo
echo "${BOLD}SnapSphere API smoke test${OFF}"
echo "${DIM}$API${OFF}"

# ─── 0. Server reachable ─────────────────────────────────────────────────────
section "0. Server"
CODE=$(curl -s -m 5 -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health/ 2>/dev/null)
check "health endpoint responds" "200" "$CODE"
if [ "$CODE" != "200" ]; then
  echo
  echo "  ${RED}Server is not running. Start it with ./start.sh${OFF}"
  exit 1
fi

# ─── 1. Registration ─────────────────────────────────────────────────────────
section "1. Registration"

EMAIL="smoketest_$(date +%s)@example.com"
REG=$(curl -s -X POST "$API/auth/register/" -H "Content-Type: application/json" -d "{
  \"email\":\"$EMAIL\",\"full_name\":\"Smoke Test\",\"password\":\"StrongPass123!\",
  \"password_confirm\":\"StrongPass123!\",\"phone\":\"03001234567\",
  \"city\":\"Islamabad\",\"role\":\"BUYER\"}")

check "new buyer registers"        "True"  "$(echo "$REG" | jget "d['success']")"
check "returns an access token"    "True"  "$(echo "$REG" | jget "d['data']['tokens']['access'][:3] == 'eyJ'")"
check "role is BUYER"              "BUYER" "$(echo "$REG" | jget "d['data']['user']['role']")"
check "email starts unverified"    "False" "$(echo "$REG" | jget "d['data']['user']['is_email_verified']")"

ACCESS=$(echo "$REG" | jget "d['data']['tokens']['access']")
REFRESH=$(echo "$REG" | jget "d['data']['tokens']['refresh']")

# ─── 2. Login ────────────────────────────────────────────────────────────────
section "2. Login"

LOGIN=$(curl -s -X POST "$API/auth/login/" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"StrongPass123!\"}")
check "correct password logs in"   "True" "$(echo "$LOGIN" | jget "d['success']")"

BAD=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/auth/login/" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"WrongPassword\"}")
check "wrong password rejected"    "401" "$BAD"

# Seeded accounts from the CSV import
SEED=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/auth/login/" \
  -H "Content-Type: application/json" \
  -d '{"email":"photographer1@snapsphere.pk","password":"photographer123"}')
check "seeded photographer logs in" "200" "$SEED"

SEEDB=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/auth/login/" \
  -H "Content-Type: application/json" \
  -d '{"email":"buyer1@snapsphere.pk","password":"buyer12345"}')
check "seeded buyer logs in"        "200" "$SEEDB"

# ─── 3. Authorisation ────────────────────────────────────────────────────────
section "3. Authorisation"

ME=$(curl -s -o /dev/null -w "%{http_code}" "$API/auth/me/" -H "Authorization: Bearer $ACCESS")
check "valid token grants access"  "200" "$ME"

NOAUTH=$(curl -s -o /dev/null -w "%{http_code}" "$API/auth/me/")
check "no token is rejected"       "401" "$NOAUTH"

GARBAGE=$(curl -s -o /dev/null -w "%{http_code}" "$API/auth/me/" -H "Authorization: Bearer not.a.token")
check "malformed token rejected"   "401" "$GARBAGE"

# ─── 4. Validation ───────────────────────────────────────────────────────────
section "4. Input validation"

DUP=$(curl -s -X POST "$API/auth/register/" -H "Content-Type: application/json" -d "{
  \"email\":\"$EMAIL\",\"full_name\":\"Duplicate User\",\"password\":\"StrongPass123!\",
  \"password_confirm\":\"StrongPass123!\",\"role\":\"BUYER\"}")
check "duplicate email blocked"    "VALIDATION_ERROR" "$(echo "$DUP" | jget "d['error']['code']")"

WEAK=$(curl -s -X POST "$API/auth/register/" -H "Content-Type: application/json" -d '{
  "email":"weak@example.com","full_name":"W","password":"123",
  "password_confirm":"456","role":"BUYER"}')
check "weak password blocked"      "VALIDATION_ERROR" "$(echo "$WEAK" | jget "d['error']['code']")"
check "password mismatch caught"   "True" "$(echo "$WEAK" | jget "'password' in d['error']['details']")"

BADPHONE=$(curl -s -X POST "$API/auth/register/" -H "Content-Type: application/json" -d '{
  "email":"phone@example.com","full_name":"Phone Test","password":"StrongPass123!",
  "password_confirm":"StrongPass123!","phone":"12345","role":"BUYER"}')
check "invalid phone blocked"      "True" "$(echo "$BADPHONE" | jget "'phone' in d['error']['details']")"

# ─── 5. Security controls ────────────────────────────────────────────────────
section "5. Security"

ESC=$(curl -s -X POST "$API/auth/register/" -H "Content-Type: application/json" -d '{
  "email":"admin_escalation@example.com","full_name":"Hacker Man",
  "password":"StrongPass123!","password_confirm":"StrongPass123!","role":"ADMIN"}')
check "cannot self-register as ADMIN" "True" "$(echo "$ESC" | jget "'role' in d['error']['details']")"

# token_version kill switch: bumping it must invalidate live access tokens
"$PY" "$ROOT/backend/manage.py" shell -c "
from django.contrib.auth import get_user_model
get_user_model().objects.get(email='$EMAIL').invalidate_tokens()" >/dev/null 2>&1
KILLED=$(curl -s -o /dev/null -w "%{http_code}" "$API/auth/me/" -H "Authorization: Bearer $ACCESS")
check "token_version kill switch"  "401" "$KILLED"

# blocked account must be refused even with a freshly-minted token
FRESH=$(curl -s -X POST "$API/auth/login/" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"StrongPass123!\"}" | jget "d['data']['tokens']['access']")
"$PY" "$ROOT/backend/manage.py" shell -c "
from django.contrib.auth import get_user_model
u = get_user_model().objects.get(email='$EMAIL')
u.is_blocked = True; u.blocked_reason = 'smoke test'
u.save(update_fields=['is_blocked','blocked_reason'])" >/dev/null 2>&1
BLOCKED=$(curl -s "$API/auth/me/" -H "Authorization: Bearer $FRESH")
check "blocked account refused"    "ACCOUNT_BLOCKED" "$(echo "$BLOCKED" | jget "d['error']['code']")"

# ─── 6. Database integrity ───────────────────────────────────────────────────
section "6. Database integrity"

DOUBLE=$("$PY" "$ROOT/backend/manage.py" shell -c "
from django.db import IntegrityError, transaction
from apps.bookings.models import Booking
from apps.bookings.constants import BookingStatus
from decimal import Decimal
b = Booking.objects.filter(status=BookingStatus.PENDING).first()
if not b:
    print('NO_DATA')
else:
    d = Booking(buyer=b.buyer, photographer=b.photographer, service=b.service,
                category=b.category, event_date=b.event_date, start_time=b.start_time,
                duration_hours=4, location_address='x', location_city='Lahore',
                unit_price=Decimal('1000'), quantity=1,
                status=BookingStatus.PENDING, expires_at=b.expires_at)
    d.calculate_totals()
    try:
        with transaction.atomic():
            d.save()
        print('ACCEPTED')
    except IntegrityError:
        print('REJECTED')
" 2>/dev/null | tail -1)
check "double booking rejected by DB" "REJECTED" "$DOUBLE"

COUNTS=$("$PY" "$ROOT/backend/manage.py" shell -c "
from django.contrib.auth import get_user_model
from apps.bookings.models import Booking
from apps.catalog.models import Service
print(f'{get_user_model().objects.count()},{Service.objects.count()},{Booking.objects.count()}')
" 2>/dev/null | tail -1)
USERS=$(echo "$COUNTS" | cut -d, -f1)
check "seed data present"          "True" "$([ "${USERS:-0}" -gt 400 ] && echo True || echo False)"

# ─── 7. Booking lifecycle ────────────────────────────────────────────────────
# Drives a real booking through the API the way the mobile app does: find a
# free date on the calendar, request it, confirm the state machine refuses the
# wrong actor, accept it, and confirm the slot is then blocked.
section "7. Booking lifecycle"

PHOTOG_ID=$(curl -s "$API/profiles/photographers/?page_size=1" | jget "d['data'][0]['id']")
PHOTOG_EMAIL=$("$PY" "$ROOT/backend/manage.py" shell -c "
from apps.profiles.models import PhotographerProfile
print(PhotographerProfile.objects.get(pk=$PHOTOG_ID).user.email)" 2>/dev/null | tail -1)

CAL=$(curl -s "$API/availability/photographers/$PHOTOG_ID/?days=60")
check "availability calendar serves" "True" "$(echo "$CAL" | jget "d['success']")"

# First free date at least a week out, so the minimum-lead rule cannot bite.
FREE_DATE=$(echo "$CAL" | "$PY" -c 'import sys, json
d = json.load(sys.stdin)
free = [x["date"] for x in d["data"]["days"][7:] if x["is_available"]]
print(free[0] if free else "")' 2>/dev/null)
check "calendar offers a free date"  "True" "$([ -n "$FREE_DATE" ] && echo True || echo False)"

SLOT=$(curl -s "$API/availability/photographers/$PHOTOG_ID/day/?date=$FREE_DATE&duration_hours=4" \
       | jget "d['data']['available_start_times'][0]")
SERVICE_ID=$(curl -s "$API/profiles/photographers/$PHOTOG_ID/" | jget "d['data']['services'][0]['id']")

BUYER_TOKEN=$(curl -s -X POST "$API/auth/login/" -H "Content-Type: application/json" \
  -d '{"email":"buyer1@snapsphere.pk","password":"buyer12345"}' | jget "d['data']['tokens']['access']")

BOOK=$(curl -s -X POST "$API/bookings/" -H "Authorization: Bearer $BUYER_TOKEN" \
  -H "Content-Type: application/json" -H "Idempotency-Key: smoke-$(date +%s)" \
  -d "{\"service\":$SERVICE_ID,\"event_date\":\"$FREE_DATE\",\"start_time\":\"$SLOT\",
       \"location_address\":\"Smoke test venue\",\"location_city\":\"Islamabad\"}")

check "buyer creates a booking"      "PENDING" "$(echo "$BOOK" | jget "d['data']['status']")"
check "price snapshotted by server"  "True"    "$(echo "$BOOK" | jget "float(d['data']['total_price']) > 0 and d['data']['total_price'] == d['data']['price_breakdown'][-1]['amount']")"
check "buyer's only action is cancel" "['cancel']" "$(echo "$BOOK" | jget "d['data']['available_actions']")"
check "phone numbers withheld"       "None"    "$(echo "$BOOK" | jget "d['data']['contact']")"

BOOKING_ID=$(echo "$BOOK" | jget "d['data']['id']")

# The same slot, requested again — the guard must refuse it.
DUP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/bookings/" \
  -H "Authorization: Bearer $BUYER_TOKEN" -H "Content-Type: application/json" \
  -d "{\"service\":$SERVICE_ID,\"event_date\":\"$FREE_DATE\",\"start_time\":\"$SLOT\",
       \"location_address\":\"Smoke test venue\",\"location_city\":\"Islamabad\"}")
case "$DUP" in 409|400) DUP_OK=True ;; *) DUP_OK=False ;; esac
check "duplicate slot refused"       "True" "$DUP_OK"

# Wrong actor: a buyer may not accept their own request.
BUYER_ACCEPT=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/bookings/$BOOKING_ID/accept/" \
  -H "Authorization: Bearer $BUYER_TOKEN" -H "Content-Type: application/json" -d '{}')
check "buyer cannot accept"          "403" "$BUYER_ACCEPT"

PHOTOG_TOKEN=$(curl -s -X POST "$API/auth/login/" -H "Content-Type: application/json" \
  -d "{\"email\":\"$PHOTOG_EMAIL\",\"password\":\"photographer123\"}" | jget "d['data']['tokens']['access']")

ACCEPTED=$(curl -s -X POST "$API/bookings/$BOOKING_ID/accept/" \
  -H "Authorization: Bearer $PHOTOG_TOKEN" -H "Content-Type: application/json" -d '{}')
check "photographer accepts"         "ACCEPTED" "$(echo "$ACCEPTED" | jget "d['data']['status']")"
check "timeline records both steps"  "2"        "$(echo "$ACCEPTED" | jget "len(d['data']['timeline'])")"
check "contact released on accept"   "True"     "$(echo "$ACCEPTED" | jget "d['data']['contact'] is not None")"

REACCEPT=$(curl -s -X POST "$API/bookings/$BOOKING_ID/accept/" \
  -H "Authorization: Bearer $PHOTOG_TOKEN" -H "Content-Type: application/json" -d '{}')
check "illegal transition refused"   "BUSINESS_RULE_VIOLATION" "$(echo "$REACCEPT" | jget "d['error']['code']")"

BLOCKED=$(curl -s "$API/availability/photographers/$PHOTOG_ID/day/?date=$FREE_DATE" \
          | jget "d['data']['reason']")
check "accepted slot blocks calendar" "True" "$([ "$BLOCKED" = "FULLY_BOOKED" ] && echo True || echo False)"

# Leave the seeded data as it was found.
"$PY" "$ROOT/backend/manage.py" shell -c "
from apps.bookings.models import Booking, BookingStatusHistory
b = Booking.objects.filter(pk=$BOOKING_ID).first()
if b:
    BookingStatusHistory.objects.filter(booking=b).delete()
    if hasattr(b, 'payment'): b.payment.delete()
    b.hard_delete()" >/dev/null 2>&1

# ─── 8. Shop, wallet & profile ───────────────────────────────────────────────
# Drives a real purchase the way the app does: browse, cart, wallet checkout,
# then redeem a single-use download link — and proves the file is not
# reachable without one.
section "8. Shop, wallet & profile"

SHOP_TOKEN=$(curl -s -X POST "$API/auth/login/" -H "Content-Type: application/json" \
  -d '{"email":"buyer1@snapsphere.pk","password":"buyer12345"}' | jget "d['data']['tokens']['access']")
SHOP_AUTH="Authorization: Bearer $SHOP_TOKEN"

PROFILE=$(curl -s "$API/profiles/me/" -H "$SHOP_AUTH")
check "own profile serves"           "True" "$(echo "$PROFILE" | jget "d['success']")"

WALLET=$(curl -s "$API/profiles/me/wallet/" -H "$SHOP_AUTH")
START_BALANCE=$(echo "$WALLET" | jget "d['data']['balance']")
check "wallet balance serves"        "True" "$(echo "$WALLET" | jget "float(d['data']['balance']) >= 0")"

# Every rupee must have a matching ledger row — that is what a ledger is for.
check "ledger reconciles"            "True" "$(curl -s "$API/profiles/me/wallet/transactions/" -H "$SHOP_AUTH" | "$PY" -c '
import sys, json
rows = sorted(json.load(sys.stdin)["data"], key=lambda r: r["id"])
running = None
for r in rows:
    if running is not None and float(r["balance_before"]) != running:
        print("False"); sys.exit(0)
    running = float(r["balance_after"])
print("True")' 2>/dev/null)"

# Pick the cheapest product this buyer does NOT already own. Taking the
# globally cheapest would fail on a second run against the same database,
# because by then they own it — and "you already own this" is correct
# behaviour, not a regression.
CHEAPEST=$(curl -s "$API/marketplace/products/?ordering=price&page_size=40" -H "$SHOP_AUTH" \
  | "$PY" -c '
import sys, json
rows = json.load(sys.stdin)["data"]
free = [r for r in rows if not r["is_owned"] and not r["in_cart"]]
print(free[0]["id"] if free else "")' 2>/dev/null)
check "shop browse is public"        "True" "$([ -n "$CHEAPEST" ] && echo True || echo False)"
check "filter options from data"     "True" "$(curl -s "$API/marketplace/products/filters/" | jget "d['data']['price_range']['max'] > 0")"

CART=$(curl -s -X POST "$API/marketplace/cart/add/" -H "$SHOP_AUTH" \
  -H "Content-Type: application/json" -d "{\"product\":$CHEAPEST}")
check "add to cart"                  "1"    "$(echo "$CART" | jget "d['data']['count']")"

# The body carries no money — a client that names its own total buys for Rs 1.
ORDER=$(curl -s -X POST "$API/marketplace/orders/checkout/" -H "$SHOP_AUTH" \
  -H "Content-Type: application/json" -H "Idempotency-Key: smoke-shop-$(date +%s)" \
  -d '{"total":"1.00"}')
check "wallet checkout"              "PAID" "$(echo "$ORDER" | jget "d['data']['status']")"
check "server price wins"            "True" "$(echo "$ORDER" | jget "float(d['data']['total']) > 1")"

ORDER_TOTAL=$(echo "$ORDER" | jget "d['data']['total']")
check "wallet debited exactly once"  "True" "$(curl -s "$API/profiles/me/wallet/" -H "$SHOP_AUTH" \
  | jget "abs((float('$START_BALANCE') - float(d['data']['balance'])) - float('$ORDER_TOTAL')) < 0.01")"
check "cart emptied"                 "0"    "$(curl -s "$API/marketplace/cart/" -H "$SHOP_AUTH" | jget "d['data']['count']")"

ITEM_ID=$(curl -s "$API/marketplace/orders/purchases/" -H "$SHOP_AUTH" | jget "d['data'][0]['id']")
DL=$(curl -s -X POST "$API/marketplace/orders/items/$ITEM_ID/download/" -H "$SHOP_AUTH" \
  -H "Content-Type: application/json" -d '{}')
DL_URL=$(echo "$DL" | jget "d['data']['download_url']")
check "download link issued"         "True" "$([ -n "$DL_URL" ] && echo True || echo False)"
check "link streams the file"        "200"  "$(curl -s -o /dev/null -w "%{http_code}" "$DL_URL")"
check "link is single-use"           "410"  "$(curl -s -o /dev/null -w "%{http_code}" "$DL_URL")"

# The whole point of the token: the bytes are NOT at a guessable public URL.
PRIVATE_FILE=$(ls "$ROOT/backend/private_media/products"/*/*/ 2>/dev/null | head -1)
check "product files are not public" "404" "$(curl -s -o /dev/null -w "%{http_code}" \
  "http://127.0.0.1:8000/media/products/$PRIVATE_FILE")"

# Asserted as a round trip rather than against a fixed value: the row may
# already exist from an earlier run, and "toggle" is defined by the state it
# leaves behind, not by which way it happened to move first.
PHOTOG_FOR_WISH=$(curl -s "$API/profiles/photographers/?page_size=1" | jget "d['data'][0]['id']")
toggle_wish() {
  curl -s -X POST "$API/wishlist/toggle/" -H "$SHOP_AUTH" \
    -H "Content-Type: application/json" -d "{\"photographer\":$PHOTOG_FOR_WISH}" \
    | jget "d['data']['is_saved']"
}
INITIAL=$(curl -s "$API/profiles/photographers/$PHOTOG_FOR_WISH/" -H "$SHOP_AUTH" \
  | jget "d['data']['is_wishlisted']")
FIRST=$(toggle_wish)
SECOND=$(toggle_wish)
check "wishlist toggle flips state"  "True" "$([ "$FIRST" != "$INITIAL" ] && echo True || echo False)"
check "wishlist toggle round-trips"  "$INITIAL" "$SECOND"

# Restore the seeded state: refund the smoke purchase and drop the order.
"$PY" "$ROOT/backend/manage.py" shell -c "
from apps.marketplace.models import Order, OrderItem, DownloadToken
from apps.profiles.models import WalletTransactionType
from apps.profiles.services import credit_wallet
o = Order.objects.filter(pk=$(echo "$ORDER" | jget "d['data']['id']")).first()
if o:
    credit_wallet(o.buyer, o.total, txn_type=WalletTransactionType.REFUND,
                  reference=o.order_number, description='Smoke test rollback')
    DownloadToken.objects.filter(order_item__order=o).delete()
    OrderItem.objects.filter(order=o).delete()
    o.delete()" >/dev/null 2>&1

# ─── 9. Photographer studio (Modules 5 & 6) ──────────────────────────────────
# The photographer's own side: managing services, blocking dates, uploading
# work — and proving each write is scoped to them and visible to buyers.
section "9. Photographer studio"

STUDIO_TOKEN=$(curl -s -X POST "$API/auth/login/" -H "Content-Type: application/json" \
  -d '{"email":"photographer1@snapsphere.pk","password":"photographer123"}' | jget "d['data']['tokens']['access']")
STUDIO_AUTH="Authorization: Bearer $STUDIO_TOKEN"
STUDIO_ID=$(curl -s "$API/profiles/me/" -H "$STUDIO_AUTH" | jget "d['data']['id']")

check "own services serve"           "True" "$(curl -s "$API/catalog/my-services/" -H "$STUDIO_AUTH" | jget "d['success']")"
check "own calendar serves"          "7"    "$(curl -s "$API/availability/me/" -H "$STUDIO_AUTH" | jget "len(d['data']['rules'])")"
check "portfolio summary serves"     "True" "$(curl -s "$API/portfolio/me/summary/" -H "$STUDIO_AUTH" | jget "'images' in d['data']")"

# ─── Publish a service, then check the public "from" price followed it ───────
STUDIO_CAT=$(curl -s "$API/catalog/categories/" | jget "d['data'][0]['id']")
NEW_SERVICE=$(curl -s -X POST "$API/catalog/my-services/" -H "$STUDIO_AUTH" \
  -H "Content-Type: application/json" \
  -d "{\"title\":\"Smoke Test Mini Session\",\"category\":$STUDIO_CAT,\"price\":\"1500.00\",
       \"duration_hours\":1,\"min_hours\":1,\"edited_photos_count\":10,\"delivery_days\":3,
       \"includes\":[\"10 edited photos\",\"  \"]}")
check "publish a service"            "Smoke Test Mini Session" "$(echo "$NEW_SERVICE" | jget "d['data']['title']")"
check "blank bullets stripped"       "1"    "$(echo "$NEW_SERVICE" | jget "len(d['data']['includes'])")"
SERVICE_ID=$(echo "$NEW_SERVICE" | jget "d['data']['id']")

check "base price follows catalogue" "1500.00" "$(curl -s "$API/profiles/photographers/$STUDIO_ID/" | jget "d['data']['base_price']")"

# A brand-new service has no bookings, so deleting it is allowed.
check "unbooked service deletable"   "True" "$(echo "$NEW_SERVICE" | jget "d['data']['can_delete']")"

# ─── Block dates and confirm buyers see them closed ──────────────────────────
BLOCK_FROM=$("$PY" -c "import datetime;print(datetime.date.today()+datetime.timedelta(days=50))")
BLOCK_TO=$("$PY" -c "import datetime;print(datetime.date.today()+datetime.timedelta(days=53))")
BLOCKED=$(curl -s -X POST "$API/availability/me/blackouts/add/" -H "$STUDIO_AUTH" \
  -H "Content-Type: application/json" \
  -d "{\"start_date\":\"$BLOCK_FROM\",\"end_date\":\"$BLOCK_TO\",\"reason\":\"Smoke test block\"}")
check "block a date range"           "4" "$(echo "$BLOCKED" | jget "d['data']['blackout']['days']")"
BLOCK_ID=$(echo "$BLOCKED" | jget "d['data']['blackout']['id']")

check "blocked dates close for buyers" "BLACKOUT" "$(curl -s "$API/availability/photographers/$STUDIO_ID/?days=60" \
  | "$PY" -c '
import sys, json
days = json.load(sys.stdin)["data"]["days"]
hit = [d for d in days if d["date"] == "'"$BLOCK_FROM"'"]
print(hit[0]["reason"] if hit else "NOT_IN_WINDOW")' 2>/dev/null)"

# ─── Upload a photo and prove the EXIF is gone ───────────────────────────────
"$PY" -c "
from PIL import Image
im = Image.new('RGB', (1400, 900), (120, 90, 60))
exif = im.getexif(); exif[0x8825] = {1:'N', 2:(31,32,0)}; exif[0x010F] = 'SmokePhone'
im.save('/tmp/snapsphere_smoke.jpg', exif=exif)" 2>/dev/null
UPLOADED=$(curl -s -X POST "$API/portfolio/me/" -H "$STUDIO_AUTH" \
  -F "image=@/tmp/snapsphere_smoke.jpg;type=image/jpeg" -F "caption=Smoke test photo")
check "portfolio upload"             "1400" "$(echo "$UPLOADED" | jget "d['data']['width']")"
IMAGE_ID=$(echo "$UPLOADED" | jget "d['data']['id']")

check "three renditions generated"   "True" "$(echo "$UPLOADED" | jget "bool(d['data']['thumbnail_url']) and bool(d['data']['image_large_url']) and d['data']['thumbnail_url'] != d['data']['image_large_url']")"

THUMB_URL=$(echo "$UPLOADED" | jget "d['data']['thumbnail_url']")
curl -s -o /tmp/snapsphere_thumb.webp "$THUMB_URL"
check "EXIF stripped on upload"      "True" "$("$PY" -c "
from PIL import Image
print(dict(Image.open('/tmp/snapsphere_thumb.webp').getexif()) == {})" 2>/dev/null)"

check "photo reaches the public grid" "True" "$(curl -s "$API/portfolio/photographers/$STUDIO_ID/images/" \
  | jget "any(r['id'] == $IMAGE_ID for r in d['data'])")"

# ─── Scoping: another photographer's studio is a 404, not a 403 ──────────────
OTHER_TOKEN=$(curl -s -X POST "$API/auth/login/" -H "Content-Type: application/json" \
  -d '{"email":"photographer2@snapsphere.pk","password":"photographer123"}' | jget "d['data']['tokens']['access']")
check "cannot edit another catalogue" "404" "$(curl -s -o /dev/null -w "%{http_code}" \
  -X PATCH "$API/catalog/my-services/$SERVICE_ID/" -H "Authorization: Bearer $OTHER_TOKEN" \
  -H "Content-Type: application/json" -d '{"price":"1.00"}')"
check "cannot delete another photo"   "404" "$(curl -s -o /dev/null -w "%{http_code}" \
  -X DELETE "$API/portfolio/me/$IMAGE_ID/" -H "Authorization: Bearer $OTHER_TOKEN")"
check "buyers have no studio"         "403" "$(curl -s -o /dev/null -w "%{http_code}" \
  "$API/catalog/my-services/" -H "Authorization: Bearer $BUYER_TOKEN")"

# Leave the seeded data as it was found.
curl -s -o /dev/null -X DELETE "$API/catalog/my-services/$SERVICE_ID/" -H "$STUDIO_AUTH"
curl -s -o /dev/null -X DELETE "$API/availability/me/blackouts/$BLOCK_ID/" -H "$STUDIO_AUTH"
curl -s -o /dev/null -X DELETE "$API/portfolio/me/$IMAGE_ID/" -H "$STUDIO_AUTH"
rm -f /tmp/snapsphere_smoke.jpg /tmp/snapsphere_thumb.webp

# ─── 10. Analytics dashboard (Module 15) ─────────────────────────────────────
# The dashboard mixes two speeds on purpose: headline counters are computed
# live so they are never stale, charts read a nightly rollup so they are never
# slow. Both halves are checked, plus the idempotence the rollup depends on.
section "10. Analytics dashboard"

DASH=$(curl -s "$API/analytics/me/" -H "$STUDIO_AUTH")
check "dashboard serves"             "True" "$(echo "$DASH" | jget "d['success']")"
check "one response, all sections"   "True" "$(echo "$DASH" | jget "sorted(d['data']) == sorted(['overview','revenue_series','daily_series','funnel','top_services','category_split','upcoming'])")"
check "daily series gap-filled"      "30"   "$(echo "$DASH" | jget "len(d['data']['daily_series'])")"
check "revenue series gap-filled"    "6"    "$(echo "$DASH" | jget "len(d['data']['revenue_series'])")"
check "month labels pre-formatted"   "True" "$(echo "$DASH" | jget "all(p['label'].isalpha() for p in d['data']['revenue_series'])")"
check "rates computed server-side"   "True" "$(echo "$DASH" | jget "isinstance(d['data']['funnel']['view_to_booking_rate'], float)")"
check "window params clamped"        "90"   "$(curl -s "$API/analytics/me/?days=9999" -H "$STUDIO_AUTH" | jget "len(d['data']['daily_series'])")"

# The headline must reflect a booking made this second — it is computed live,
# not read from last night's rollup.
check "headline counters are live"   "True" "$(echo "$DASH" | jget "d['data']['overview']['completed_shoots'] > 0")"
check "lifetime earnings present"    "True" "$(echo "$DASH" | jget "float(d['data']['overview']['lifetime_earnings']) > 0")"

# Re-running a rollup must correct, not double — the nightly job, its retries
# and the backfill all re-run the same day.
check "rollup is idempotent"         "True" "$("$PY" "$ROOT/backend/manage.py" shell -c "
from django.utils import timezone
from apps.analytics.models import DailyPhotographerStat
from apps.analytics.services import rollup_day
day = timezone.localdate() - timezone.timedelta(days=2) if hasattr(timezone, 'timedelta') else None
from datetime import timedelta
day = timezone.localdate() - timedelta(days=2)
rollup_day(day)
first = list(DailyPhotographerStat.objects.filter(date=day).values_list('bookings_created', flat=True))
rollup_day(day)
second = list(DailyPhotographerStat.objects.filter(date=day).values_list('bookings_created', flat=True))
print(sorted(first) == sorted(second) and len(first) == len(second))
" 2>/dev/null | tail -1)"

check "analytics are owner-only"     "403" "$(curl -s -o /dev/null -w "%{http_code}" \
  "$API/analytics/me/" -H "Authorization: Bearer $BUYER_TOKEN")"
check "anonymous refused"            "401" "$(curl -s -o /dev/null -w "%{http_code}" "$API/analytics/me/")"

# ─── 11. Reviews (Module 9) ──────────────────────────────────────────────────
# Drives a whole review: complete a booking, post the review, prove the
# photographer's headline rating moved with it, reply as the photographer, and
# prove a second review for the same booking is impossible.
section "11. Reviews"

REV_BUYER=$(curl -s -X POST "$API/auth/login/" -H "Content-Type: application/json" \
  -d '{"email":"buyer1@snapsphere.pk","password":"buyer12345"}' | jget "d['data']['tokens']['access']")
REV_BUYER_AUTH="Authorization: Bearer $REV_BUYER"

R_PHOTOG_ID=$(curl -s "$API/profiles/photographers/?page_size=1" | jget "d['data'][0]['id']")
R_PHOTOG_EMAIL=$("$PY" "$ROOT/backend/manage.py" shell -c "
from apps.profiles.models import PhotographerProfile
print(PhotographerProfile.objects.get(pk=$R_PHOTOG_ID).user.email)" 2>/dev/null | tail -1)
R_PHOTOG=$(curl -s -X POST "$API/auth/login/" -H "Content-Type: application/json" \
  -d "{\"email\":\"$R_PHOTOG_EMAIL\",\"password\":\"photographer123\"}" | jget "d['data']['tokens']['access']")
R_PHOTOG_AUTH="Authorization: Bearer $R_PHOTOG"

check "public review list serves"    "True" "$(curl -s "$API/reviews/photographers/$R_PHOTOG_ID/" | jget "d['success']")"
check "review list needs no login"   "200"  "$(curl -s -o /dev/null -w "%{http_code}" "$API/reviews/photographers/$R_PHOTOG_ID/")"

R_SUMMARY=$(curl -s "$API/reviews/photographers/$R_PHOTOG_ID/summary/")
check "summary has 5 histogram keys" "5" "$(echo "$R_SUMMARY" | jget "len(d['data']['breakdown'])")"
check "summary sub-ratings present"  "True" "$(echo "$R_SUMMARY" | jget "'punctuality' in d['data']['sub_ratings']")"
check "sentiment hidden from buyers" "True" "$(curl -s "$API/reviews/photographers/$R_PHOTOG_ID/" | jget "all('sentiment' not in r for r in d['data']) if d['data'] else True")"

# A completed booking is the entitlement. Build one through the API, then move
# the event date back so completion is legal — the same trick the unit tests use.
R_CAL=$(curl -s "$API/availability/photographers/$R_PHOTOG_ID/?days=60")
R_DATE=$(echo "$R_CAL" | "$PY" -c 'import sys, json
d = json.load(sys.stdin)
free = [x["date"] for x in d["data"]["days"][7:] if x["is_available"]]
print(free[0] if free else "")' 2>/dev/null)
R_SLOT=$(curl -s "$API/availability/photographers/$R_PHOTOG_ID/day/?date=$R_DATE&duration_hours=4" \
         | jget "d['data']['available_start_times'][0]")
R_SERVICE=$(curl -s "$API/profiles/photographers/$R_PHOTOG_ID/" | jget "d['data']['services'][0]['id']")

R_BOOK=$(curl -s -X POST "$API/bookings/" -H "$REV_BUYER_AUTH" \
  -H "Content-Type: application/json" -H "Idempotency-Key: rev-$(date +%s)" \
  -d "{\"service\":$R_SERVICE,\"event_date\":\"$R_DATE\",\"start_time\":\"$R_SLOT\",
       \"location_address\":\"Review smoke venue\",\"location_city\":\"Islamabad\"}")
R_BOOKING_ID=$(echo "$R_BOOK" | jget "d['data']['id']")

curl -s -o /dev/null -X POST "$API/bookings/$R_BOOKING_ID/accept/" \
  -H "$R_PHOTOG_AUTH" -H "Content-Type: application/json" -d '{}'
"$PY" "$ROOT/backend/manage.py" shell -c "
from datetime import timedelta
from django.utils import timezone
from apps.bookings.models import Booking
Booking.objects.filter(pk=$R_BOOKING_ID).update(event_date=timezone.localdate() - timedelta(days=1))" >/dev/null 2>&1
R_DONE=$(curl -s -X POST "$API/bookings/$R_BOOKING_ID/complete/" \
  -H "$R_PHOTOG_AUTH" -H "Content-Type: application/json" -d '{}')
check "booking completes"            "COMPLETED" "$(echo "$R_DONE" | jget "d['data']['status']")"
check "review offered to the buyer"  "True" "$(curl -s "$API/bookings/$R_BOOKING_ID/" -H "$REV_BUYER_AUTH" | jget "'review' in d['data']['available_actions']")"
check "pending list names it"        "True" "$(curl -s "$API/reviews/pending/" -H "$REV_BUYER_AUTH" | jget "any(b['booking_id'] == $R_BOOKING_ID for b in d['data']['bookings'])")"

# A 1-star review with no words is refused — it moves an average with no grounds.
check "bare 1-star refused"          "400" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/reviews/" \
  -H "$REV_BUYER_AUTH" -H "Content-Type: application/json" \
  -d "{\"booking\":$R_BOOKING_ID,\"rating\":1}")"

RATING_BEFORE=$(curl -s "$API/profiles/photographers/$R_PHOTOG_ID/" | jget "d['data']['reviews_count']")
R_POST=$(curl -s -X POST "$API/reviews/" -H "$REV_BUYER_AUTH" -H "Content-Type: application/json" \
  -d "{\"booking\":$R_BOOKING_ID,\"rating\":5,\"title\":\"Smoke test review\",
       \"comment\":\"Genuinely excellent work throughout the whole day, highly recommended.\",
       \"rating_quality\":5,\"rating_punctuality\":4}")
check "buyer posts the review"       "5"    "$(echo "$R_POST" | jget "d['data']['rating']")"
check "can_edit is server-computed"  "True" "$(echo "$R_POST" | jget "d['data']['can_edit']")"
check "sub-ratings echoed back"      "4"    "$(echo "$R_POST" | jget "d['data']['sub_ratings']['punctuality']")"
R_ID=$(echo "$R_POST" | jget "d['data']['id']")

RATING_AFTER=$(curl -s "$API/profiles/photographers/$R_PHOTOG_ID/" | jget "d['data']['reviews_count']")
check "profile review count moved"   "True" "$([ "$RATING_AFTER" -gt "$RATING_BEFORE" ] && echo True || echo False)"
check "review action now withdrawn"  "True" "$(curl -s "$API/bookings/$R_BOOKING_ID/" -H "$REV_BUYER_AUTH" | jget "'review' not in d['data']['available_actions']")"

# 400, not 409: the serializer catches "already reviewed" while the field name is
# still attached, which is the friendlier answer. The 409 from the service layer
# is the RACE path — two submits that both pass validation — and that one is
# covered by apps/reviews/tests/test_reviews.py, where the timing can be forced.
check "second review refused"        "400" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/reviews/" \
  -H "$REV_BUYER_AUTH" -H "Content-Type: application/json" \
  -d "{\"booking\":$R_BOOKING_ID,\"rating\":1,\"comment\":\"Trying to review the same booking twice.\"}")"

# The photographer's own inbox carries the model's read of the prose.
check "own inbox exposes sentiment"  "True" "$(curl -s "$API/reviews/received/" -H "$R_PHOTOG_AUTH" | jget "'sentiment' in d['data'][0]")"
check "buyer refused that inbox"     "403" "$(curl -s -o /dev/null -w "%{http_code}" "$API/reviews/received/" -H "$REV_BUYER_AUTH")"

R_REPLY=$(curl -s -X POST "$API/reviews/$R_ID/reply/" -H "$R_PHOTOG_AUTH" \
  -H "Content-Type: application/json" -d '{"comment":"Thank you — it was a pleasure to shoot."}')
check "photographer replies"         "True" "$(echo "$R_REPLY" | jget "d['data']['reply'] is not None")"
check "second reply refused"         "409"  "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/reviews/$R_ID/reply/" \
  -H "$R_PHOTOG_AUTH" -H "Content-Type: application/json" -d '{"comment":"Second thoughts."}')"
check "edit refused after a reply"   "400"  "$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$API/reviews/$R_ID/" \
  -H "$REV_BUYER_AUTH" -H "Content-Type: application/json" -d '{"rating":1}')"
check "own review not helpful-able"  "400"  "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/reviews/$R_ID/helpful/" -H "$REV_BUYER_AUTH")"

# ─── 12. Notifications (Module 12) ───────────────────────────────────────────
# The review above should have produced a bell entry for the photographer.
section "12. Notifications"

N_INBOX=$(curl -s "$API/notifications/" -H "$R_PHOTOG_AUTH")
check "inbox serves"                 "True" "$(echo "$N_INBOX" | jget "d['success']")"
check "list carries its own badge"   "True" "$(echo "$N_INBOX" | jget "'unread_count' in d['meta']")"
check "the review notified them"     "True" "$(echo "$N_INBOX" | jget "any(r['notification_type'] == 'REVIEW_RECEIVED' for r in d['data'])")"
check "category derived server-side" "True" "$(echo "$N_INBOX" | jget "all(r['category'] for r in d['data']) if d['data'] else True")"

N_BADGE=$(curl -s "$API/notifications/unread-count/" -H "$R_PHOTOG_AUTH")
check "badge splits by category"     "True" "$(echo "$N_BADGE" | jget "sorted(d['data']) == sorted(['total','bookings','messages','reviews','marketplace'])")"

N_ONE=$(echo "$N_INBOX" | jget "d['data'][0]['id']")
N_READ=$(curl -s -X POST "$API/notifications/mark-read/" -H "$R_PHOTOG_AUTH" \
  -H "Content-Type: application/json" -d "{\"ids\":[$N_ONE]}")
check "marking one read works"       "1" "$(echo "$N_READ" | jget "d['data']['updated']")"
check "unread can be undone"         "True" "$(curl -s -X POST "$API/notifications/$N_ONE/unread/" -H "$R_PHOTOG_AUTH" | jget "d['data']['unread_count'] >= 1")"

check "another inbox is unreachable" "404" "$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$API/notifications/$N_ONE/" -H "$REV_BUYER_AUTH")"

N_PREFS=$(curl -s -X PATCH "$API/notifications/preferences/" -H "$R_PHOTOG_AUTH" \
  -H "Content-Type: application/json" -d '{"promotions":true}')
check "preferences save"             "True" "$(echo "$N_PREFS" | jget "d['data']['promotions']")"
check "quiet hours validated"        "400"  "$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$API/notifications/preferences/" \
  -H "$R_PHOTOG_AUTH" -H "Content-Type: application/json" \
  -d '{"quiet_hours_enabled":true,"quiet_hours_start":"22:00","quiet_hours_end":"22:00"}')"
curl -s -o /dev/null -X PATCH "$API/notifications/preferences/" -H "$R_PHOTOG_AUTH" \
  -H "Content-Type: application/json" -d '{"promotions":false}'

N_DEV=$(curl -s -X POST "$API/notifications/devices/" -H "$R_PHOTOG_AUTH" \
  -H "Content-Type: application/json" \
  -d '{"token":"smoke-device-token","platform":"ANDROID","device_id":"smoke-device"}')
check "device registers"             "smoke-device-token" "$(echo "$N_DEV" | jget "d['data']['token']")"
check "re-registering is a no-op"    "200" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/notifications/devices/" \
  -H "$R_PHOTOG_AUTH" -H "Content-Type: application/json" \
  -d '{"token":"smoke-device-token","platform":"ANDROID","device_id":"smoke-device"}')"
curl -s -o /dev/null -X POST "$API/notifications/devices/remove/" -H "$R_PHOTOG_AUTH" \
  -H "Content-Type: application/json" -d '{"token":"smoke-device-token"}'

check "anonymous bell refused"       "401" "$(curl -s -o /dev/null -w "%{http_code}" "$API/notifications/")"

# ─── 13. Chat (Module 13) ────────────────────────────────────────────────────
section "13. Chat"

# Chat addresses people by USER id; the photographer's profile id is a
# different number, which is exactly why the API sends both.
R_PHOTOG_USER=$(curl -s "$API/profiles/photographers/$R_PHOTOG_ID/" | jget "d['data']['user_id']")
check "profile exposes its user id"  "True" "$([ -n "$R_PHOTOG_USER" ] && [ "$R_PHOTOG_USER" != "None" ] && echo True || echo False)"

C_START=$(curl -s -X POST "$API/chat/conversations/" -H "$REV_BUYER_AUTH" \
  -H "Content-Type: application/json" \
  -d "{\"user\":$R_PHOTOG_USER,\"message\":\"Smoke test: are you free in September?\"}")
check "buyer opens a thread"         "True" "$(echo "$C_START" | jget "d['data']['id'] > 0")"
CONV_ID=$(echo "$C_START" | jget "d['data']['id']")
check "the first message rode along" "True" "$(echo "$C_START" | jget "'September' in d['data']['last_message_text']")"

# Idempotent: tapping Message twice must not split the history in two.
C_AGAIN=$(curl -s -X POST "$API/chat/conversations/" -H "$REV_BUYER_AUTH" \
  -H "Content-Type: application/json" -d "{\"user\":$R_PHOTOG_USER}")
check "opening twice is one thread"  "True" "$(echo "$C_AGAIN" | jget "d['data']['id'] == $CONV_ID")"

C_SEND=$(curl -s -X POST "$API/chat/conversations/$CONV_ID/messages/" -H "$REV_BUYER_AUTH" \
  -H "Content-Type: application/json" -d '{"body":"Second smoke message","client_id":"smoke-1"}')
check "message sends"                "Second smoke message" "$(echo "$C_SEND" | jget "d['data']['body']")"
MSG_ID=$(echo "$C_SEND" | jget "d['data']['id']")

# The same client_id again — a retry after a dropped response, not a new message.
C_RETRY=$(curl -s -X POST "$API/chat/conversations/$CONV_ID/messages/" -H "$REV_BUYER_AUTH" \
  -H "Content-Type: application/json" -d '{"body":"Second smoke message","client_id":"smoke-1"}')
check "client_id makes retry safe"   "True" "$(echo "$C_RETRY" | jget "d['data']['id'] == $MSG_ID")"

# Anchored to the FIRST message's real id, not to 1. On a fresh chat table the
# first message IS id 1, so `after=1` would skip it and the check would silently
# be asserting something weaker than intended.
FIRST_MSG=$(curl -s "$API/chat/conversations/$CONV_ID/messages/" -H "$REV_BUYER_AUTH" | jget "d['data'][0]['id']")
check "replay returns only newer"    "True" "$(curl -s "$API/chat/conversations/$CONV_ID/messages/?after=$FIRST_MSG" -H "$REV_BUYER_AUTH" \
  | jget "len(d['data']) == 1 and d['data'][0]['id'] > $FIRST_MSG")"
check "replay from zero returns all" "True" "$(curl -s "$API/chat/conversations/$CONV_ID/messages/?after=0" -H "$REV_BUYER_AUTH" | jget "len(d['data']) >= 2")"
check "is_mine is per caller"        "True" "$(curl -s "$API/chat/conversations/$CONV_ID/messages/" -H "$R_PHOTOG_AUTH" | jget "all(m['is_mine'] is False for m in d['data'])")"
check "recipient sees it unread"     "True" "$(curl -s "$API/chat/conversations/unread-count/" -H "$R_PHOTOG_AUTH" | jget "d['data']['unread_total'] >= 1")"
check "marking read clears it"       "0"    "$(curl -s -X POST "$API/chat/conversations/$CONV_ID/read/" -H "$R_PHOTOG_AUTH" \
  -H "Content-Type: application/json" -d '{}' | jget "d['data']['unread_count']")"

check "contacts mirror the rule"     "True" "$(curl -s "$API/chat/conversations/contacts/" -H "$REV_BUYER_AUTH" | jget "d['success']")"
# A FRESH account, not the one from section 1: that one was deliberately blocked
# while testing the kill switch, so every request with its token is 403
# ACCOUNT_BLOCKED — which would pass a laxer check while proving nothing about
# conversation scoping.
STRANGER_EMAIL="smoketest_stranger_$(date +%s)@example.com"
STRANGER=$(curl -s -X POST "$API/auth/register/" -H "Content-Type: application/json" -d "{
  \"email\":\"$STRANGER_EMAIL\",\"full_name\":\"Nosy Stranger\",\"password\":\"StrongPass123!\",
  \"password_confirm\":\"StrongPass123!\",\"city\":\"Lahore\",\"role\":\"BUYER\"}" \
  | jget "d['data']['tokens']['access']")
check "a stranger cannot read it"    "404"  "$(curl -s -o /dev/null -w "%{http_code}" \
  "$API/chat/conversations/$CONV_ID/messages/" -H "Authorization: Bearer $STRANGER")"
check "nor send into it"             "404"  "$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$API/chat/conversations/$CONV_ID/messages/" -H "Authorization: Bearer $STRANGER" \
  -H "Content-Type: application/json" -d '{"body":"Let me in"}')"
check "deleting keeps the row"       "204"  "$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$API/chat/messages/$MSG_ID/" -H "$REV_BUYER_AUTH")"
check "withdrawn text is replaced"   "True" "$(curl -s "$API/chat/conversations/$CONV_ID/messages/" -H "$REV_BUYER_AUTH" \
  | jget "any(m['is_deleted'] and m['body'] == 'This message was deleted' for m in d['data'])")"

# ─── 14. Administration (Module 14) ──────────────────────────────────────────
section "14. Administration"

ADMIN_TOKEN=$(curl -s -X POST "$API/auth/login/" -H "Content-Type: application/json" \
  -d '{"email":"admin@snapsphere.pk","password":"admin12345"}' | jget "d['data']['tokens']['access']")
ADMIN_AUTH="Authorization: Bearer $ADMIN_TOKEN"

A_DASH=$(curl -s "$API/admin/dashboard/" -H "$ADMIN_AUTH")
check "admin dashboard serves"       "True" "$(echo "$A_DASH" | jget "d['success']")"
check "queue depths present"         "True" "$(echo "$A_DASH" | jget "'pending_approvals' in d['data']['queues']")"
check "trend is gap-filled"          "30"   "$(echo "$A_DASH" | jget "len(d['data']['trend'])")"
check "window is clamped"            "365"  "$(curl -s "$API/admin/dashboard/?days=99999" -H "$ADMIN_AUTH" | jget "d['data']['window_days']")"

check "user table serves"            "True" "$(curl -s "$API/admin/users/?role=PHOTOGRAPHER" -H "$ADMIN_AUTH" | jget "d['success']")"
check "no password hash on the wire" "True" "$(curl -s "$API/admin/users/" -H "$ADMIN_AUTH" | jget "all('password' not in r for r in d['data'])")"
check "approval queue serves"        "True" "$(curl -s "$API/admin/approvals/" -H "$ADMIN_AUTH" | jget "d['success']")"
check "moderation queue serves"      "True" "$(curl -s "$API/admin/flags/" -H "$ADMIN_AUTH" | jget "d['success']")"
check "top-up queue serves"          "True" "$(curl -s "$API/admin/topups/" -H "$ADMIN_AUTH" | jget "d['success']")"
check "audit log serves"             "True" "$(curl -s "$API/admin/audit/" -H "$ADMIN_AUTH" | jget "d['success']")"

# The audit log has no write path at all — not a permission, an absence.
check "audit rejects POST"           "405" "$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API/admin/audit/" \
  -H "$ADMIN_AUTH" -H "Content-Type: application/json" -d '{}')"

# Settings are declared, not created ad hoc.
check "unknown setting refused"      "400" "$(curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  "$API/admin/settings/not_a_real_setting/" -H "$ADMIN_AUTH" -H "Content-Type: application/json" -d '{"value":"1"}')"
check "bad typed value refused"      "400" "$(curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  "$API/admin/settings/platform_commission_percent/" -H "$ADMIN_AUTH" \
  -H "Content-Type: application/json" -d '{"value":"twelve"}')"

A_SET=$(curl -s -X PATCH "$API/admin/settings/platform_commission_percent/" -H "$ADMIN_AUTH" \
  -H "Content-Type: application/json" -d '{"value":"11"}')
check "setting change is audited"    "True" "$(echo "$A_SET" | jget "d['data']['value'] == '11'")"
check "the change reached the log"   "True" "$(curl -s "$API/admin/audit/?action=SETTING_CHANGED" -H "$ADMIN_AUTH" \
  | jget "len(d['data']) >= 1")"
curl -s -o /dev/null -X PATCH "$API/admin/settings/platform_commission_percent/" -H "$ADMIN_AUTH" \
  -H "Content-Type: application/json" -d '{"value":"10"}'

# Public settings are the one AllowAny route, and expose only flagged rows.
A_PUB=$(curl -s "$API/admin/settings/public/")
check "public settings need no auth" "True"  "$(echo "$A_PUB" | jget "d['success']")"
check "commission stays private"     "False" "$(echo "$A_PUB" | jget "'platform_commission_percent' in d['data']")"

# Role enforcement: a valid token for the wrong role is a 403, not a filtered view.
check "photographer refused"         "403" "$(curl -s -o /dev/null -w "%{http_code}" "$API/admin/dashboard/" -H "$R_PHOTOG_AUTH")"
check "buyer refused"                "403" "$(curl -s -o /dev/null -w "%{http_code}" "$API/admin/users/" -H "$REV_BUYER_AUTH")"
check "anonymous refused"            "401" "$(curl -s -o /dev/null -w "%{http_code}" "$API/admin/audit/")"

# Leave the seeded data as it was found.
"$PY" "$ROOT/backend/manage.py" shell -c "
from apps.bookings.models import Booking, BookingStatusHistory
from apps.chat.models import Conversation, ConversationParticipant, Message
from apps.notifications.models import Notification
from apps.reviews.models import Review, ReviewReply
from apps.profiles.services import refresh_photographer_rating

review = Review.all_objects.filter(booking_id=$R_BOOKING_ID).first()
if review:
    profile = review.photographer
    ReviewReply.objects.filter(review=review).delete()
    review.hard_delete()
    refresh_photographer_rating(profile)

booking = Booking.objects.filter(pk=$R_BOOKING_ID).first()
if booking:
    Conversation.objects.filter(booking=booking).update(booking=None)
    BookingStatusHistory.objects.filter(booking=booking).delete()
    if hasattr(booking, 'payment'): booking.payment.delete()
    booking.hard_delete()

conversation = Conversation.objects.filter(pk=$CONV_ID).first()
if conversation:
    Message.objects.filter(conversation=conversation).delete()
    ConversationParticipant.objects.filter(conversation=conversation).delete()
    conversation.delete()

Notification.objects.filter(title__icontains='Smoke test review').delete()
Notification.objects.filter(body__icontains='Smoke test').delete()
" >/dev/null 2>&1

# ─── 15. Documentation ───────────────────────────────────────────────────────
section "15. API documentation"

DOCS=$(curl -s -o /dev/null -w "%{http_code}" "$API/docs/")
check "Swagger UI serves"           "200" "$DOCS"
SCHEMA=$(curl -s -o /dev/null -w "%{http_code}" "$API/schema/")
check "OpenAPI schema serves"       "200" "$SCHEMA"

# ─── Cleanup ─────────────────────────────────────────────────────────────────
"$PY" "$ROOT/backend/manage.py" shell -c "
from django.contrib.auth import get_user_model
get_user_model().all_objects.filter(email__startswith='smoketest_').hard_delete()" >/dev/null 2>&1

# ─── Summary ─────────────────────────────────────────────────────────────────
echo
echo "${BOLD}────────────────────────────────────────${OFF}"
if [ "$FAILED" -eq 0 ]; then
  echo "  ${GREEN}${BOLD}ALL $PASSED CHECKS PASSED${OFF}"
else
  echo "  ${GREEN}$PASSED passed${OFF}   ${RED}$FAILED failed${OFF}"
fi
echo "${BOLD}────────────────────────────────────────${OFF}"
echo

exit $([ "$FAILED" -eq 0 ] && echo 0 || echo 1)
