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

# ─── 9. Documentation ────────────────────────────────────────────────────────
section "9. API documentation"

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
