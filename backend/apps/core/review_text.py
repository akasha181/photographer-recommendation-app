"""
Photography review prose generator, used for seeding demo data.

WHY NOT JUST USE yelp.csv TEXT
------------------------------
yelp.csv is the right corpus for TRAINING the sentiment classifier: 44,610
genuinely human-written reviews with trustworthy star labels, and the
linguistic markers of satisfaction ("exceeded expectations", "would not
recommend") transfer across domains. That is a sound modelling decision and
ml/pipelines/train_sentiment.py keeps using it.

It is the wrong source for DISPLAY text. Yelp reviews are about restaurants,
so a seeded photographer profile ends up showing "one of the best dining
experiences we had in Phoenix" under a wedding portfolio. In a demo that
reads as a bug, and it makes the review screens impossible to evaluate.

So display text is generated here instead: combinatorial templates in the
right domain, tone-matched to the star rating. Roughly 10^4 distinct
combinations per star level, which is ample for 50k seeded rows without
visible repetition.
"""

import random

# ═══════════════════════════════════════════════════════════════════════════
# 5 STAR — delighted
# ═══════════════════════════════════════════════════════════════════════════
FIVE_OPEN = [
    "Absolutely thrilled with how the photos turned out.",
    "Genuinely exceeded every expectation we had.",
    "Could not have asked for a better experience.",
    "Hands down the best decision we made for our event.",
    "Worth every single rupee and then some.",
    "We are still getting compliments on these photos.",
    "From the first message to the final gallery, flawless.",
    "I have booked photographers before, but never like this.",
    "Everything about the shoot was perfect.",
    "Beyond happy with the entire experience.",
]
FIVE_BODY = [
    "The lighting and composition are stunning throughout.",
    "Every candid moment we hoped for was captured, and several we did not expect.",
    "The editing is tasteful — natural, not over-processed.",
    "They knew exactly where to stand and when to shoot.",
    "The colours are rich and the skin tones look completely natural.",
    "Made everyone feel relaxed, which shows in how genuine the photos look.",
    "The group shots were organised quickly without anyone feeling rushed.",
    "Arrived early, scouted the venue and had a plan before we even started.",
    "Handled the low indoor light beautifully without harsh flash.",
    "The detail shots of the decor and outfits were gorgeous.",
    "Caught my grandmother laughing in a way I will treasure forever.",
    "Even the guests commented on how professional the whole setup was.",
]
FIVE_CLOSE = [
    "Delivered the full gallery ahead of schedule.",
    "Already recommended them to two friends.",
    "Will absolutely book again for our next event.",
    "Communication throughout was quick and clear.",
    "Highly recommended to anyone on the fence.",
    "Ten out of ten, no hesitation.",
    "Truly a professional in every sense.",
]

# ═══════════════════════════════════════════════════════════════════════════
# 4 STAR — happy, minor niggle
# ═══════════════════════════════════════════════════════════════════════════
FOUR_OPEN = [
    "Really happy with the results overall.",
    "Great experience and lovely photos.",
    "Very solid work, we are pleased.",
    "Would definitely recommend them.",
    "Good value and a professional approach.",
    "The photos came out lovely.",
    "A genuinely positive experience.",
]
FOUR_BODY = [
    "The portraits in particular are beautiful.",
    "Captured the key moments we asked for.",
    "Editing is clean and consistent across the set.",
    "Very easy to work with on the day.",
    "Good eye for framing and background.",
    "Handled a fairly chaotic event calmly.",
    "The candid shots are the standout for me.",
]
FOUR_CLOSE = [
    "Delivery took a little longer than quoted, but the quality made up for it.",
    "A few more wide shots would have been nice, but no real complaints.",
    "Only small thing was slow replies in the first week.",
    "Would have liked a couple more edits, otherwise excellent.",
    "Minor delay in delivery but well worth the wait.",
    "Would book again without hesitation.",
    "Very close to perfect.",
]

# ═══════════════════════════════════════════════════════════════════════════
# 3 STAR — mixed
# ═══════════════════════════════════════════════════════════════════════════
THREE_OPEN = [
    "Decent work, though not quite what I pictured.",
    "Mixed feelings about this one.",
    "It was fine — nothing wrong, nothing memorable.",
    "Average experience overall.",
    "Some good photos, some misses.",
    "Okay, but I expected more for the price.",
]
THREE_BODY = [
    "About half the set is genuinely lovely, the rest is a bit flat.",
    "The posed shots are good but the candids are hit and miss.",
    "Editing felt slightly inconsistent between shots.",
    "A few key moments were missed while they were changing lenses.",
    "The indoor photos are noticeably darker than the outdoor ones.",
    "Communication was fine but not especially proactive.",
]
THREE_CLOSE = [
    "Delivery was on time at least.",
    "Would consider them again for a smaller event.",
    "Reasonable for the price, but shop around.",
    "Not bad, not brilliant.",
    "Might suit someone with simpler requirements.",
]

# ═══════════════════════════════════════════════════════════════════════════
# 2 STAR — disappointed
# ═══════════════════════════════════════════════════════════════════════════
TWO_OPEN = [
    "Unfortunately this did not go the way we hoped.",
    "Disappointed, especially given the price.",
    "Not the experience we were promised.",
    "Struggled to get what we actually asked for.",
    "Would think twice before booking again.",
]
TWO_BODY = [
    "A number of shots are noticeably out of focus.",
    "Several important moments were missed entirely.",
    "The editing is heavy-handed and the skin tones look off.",
    "Arrived late and seemed unprepared for the venue.",
    "We had to chase repeatedly for the final gallery.",
    "The brief we discussed beforehand was largely ignored.",
]
TWO_CLOSE = [
    "Delivery was weeks past the agreed date.",
    "Responses became very slow after payment.",
    "Some usable photos, but not what we paid for.",
    "Left us doing a lot of the organising ourselves.",
]

# ═══════════════════════════════════════════════════════════════════════════
# 1 STAR — bad
# ═══════════════════════════════════════════════════════════════════════════
ONE_OPEN = [
    "Very poor experience, would not recommend.",
    "Regret booking this photographer.",
    "Genuinely disappointing from start to finish.",
    "Save your money and look elsewhere.",
    "This did not work out at all.",
]
ONE_BODY = [
    "Most of the photos are blurry or badly framed.",
    "Turned up over an hour late with no explanation.",
    "Stopped replying to messages entirely after the shoot.",
    "The gallery we received looks nothing like the portfolio.",
    "Missed the entire ceremony while setting up equipment.",
    "Unprofessional conduct in front of our guests.",
]
ONE_CLOSE = [
    "Took months to deliver and we had to chase constantly.",
    "No apology, no attempt to make it right.",
    "A genuinely upsetting outcome for an important day.",
    "Had to ask a guest's photos to fill the gaps.",
]

_BY_STAR = {
    5: (FIVE_OPEN, FIVE_BODY, FIVE_CLOSE),
    4: (FOUR_OPEN, FOUR_BODY, FOUR_CLOSE),
    3: (THREE_OPEN, THREE_BODY, THREE_CLOSE),
    2: (TWO_OPEN, TWO_BODY, TWO_CLOSE),
    1: (ONE_OPEN, ONE_BODY, ONE_CLOSE),
}

TITLES = {
    5: ["Absolutely brilliant", "Exceeded expectations", "Could not be happier",
        "Worth every rupee", "Outstanding work", "Beautiful photos"],
    4: ["Really good", "Very happy", "Great work", "Would recommend",
        "Lovely photos", "Solid experience"],
    3: ["Decent, with caveats", "Mixed feelings", "Average", "Okay overall",
        "Some good, some not"],
    2: ["Disappointing", "Not what we expected", "Below par",
        "Would think twice", "Fell short"],
    1: ["Very poor", "Would not recommend", "Regret booking",
        "Avoid", "Bad experience"],
}


def review_text(stars: int, category: str | None = None) -> str:
    """
    Build one review body for the given star rating.

    Sentence count varies with rating: happy reviewers write more, and a
    corpus where every review is exactly three sentences looks synthetic at a
    glance.
    """
    stars = max(1, min(5, int(stars)))
    openers, bodies, closers = _BY_STAR[stars]

    parts = [random.choice(openers), random.choice(bodies)]
    if random.random() < (0.75 if stars >= 4 else 0.55):
        parts.append(random.choice(closers))
    if stars >= 4 and category and random.random() < 0.3:
        parts.insert(1, f"We booked them for a {category.lower()} shoot.")

    return " ".join(parts)


def review_title(stars: int) -> str:
    return random.choice(TITLES[max(1, min(5, int(stars)))])
