import re
from geotext import GeoText
from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.validators.scraped_job_validator import ScrapedJobValidator

# ==========================================
# POLICY
# ==========================================
# This validator optimizes for ZERO FALSE NEGATIVES on real US jobs, even at
# the cost of occasionally accepting a non-US job (an "acceptable false
# positive"). Concretely:
#
#   - A bare 2-letter token that matches a US state abbreviation (IL, CA, DE,
#     GA, LA, ME, PA, IN, ...) is ALWAYS trusted, even though these same two
#     letters also happen to be real country codes (IL=Israel, CA=Canada,
#     DE=Germany, GA=Gabon, LA=Laos, ME=Montenegro, PA=Panama, IN=India).
#     We would rather keep a handful of "Tel Aviv, IL" / "Frankfurt, DE"
#     style postings than risk dropping a real Springfield, IL or
#     Wilmington, DE job.
#   - We only reject a listing when there is an UNAMBIGUOUS non-US signal
#     with no competing US signal at all: an explicit, fully spelled-out
#     foreign country/region name (never a bare abbreviation), or a known
#     foreign city with no accompanying US state token.
#
# This means the same two letters can lead to opposite outcomes depending on
# what else is in the string:
#   "Tel Aviv, IL"        -> True  (IL token collision, trust it)
#   "Tel Aviv"            -> False (no US token at all, and city is known intl)
#   "Tel Aviv, IL, USA"   -> True  (explicit country override, also True anyway)
#
# ==========================================
# CONSTANTS
# ==========================================
US_COUNTRY_PATTERNS = [r"\bunited states\b", r"\bu\.s\.a?\.?\b", r"\busa\b", r"\bus\b"]
US_COUNTRY_REGEX = re.compile("|".join(US_COUNTRY_PATTERNS), re.IGNORECASE)

US_STATE_ABBR = [
    "al","ak","az","ar","ca","co","ct","de","fl","ga","hi","id","il","in",
    "ia","ks","ky","la","me","md","ma","mi","mn","ms","mo","mt","ne","nv",
    "nh","nj","nm","ny","nc","nd","oh","ok","or","pa","ri","sc","sd","tn",
    "tx","ut","vt","va","wa","wv","wi","wy","dc",
]

# US territories: not one of the 50 states, but still a US jurisdiction, so
# their 2-letter codes must be whitelisted too or the "unrecognized 2-letter
# code = foreign" rule below would wrongly reject them.
US_TERRITORY_ABBR = ["pr", "gu", "vi", "as", "mp"]

US_STATE_NAMES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "west virginia", "wisconsin", "wyoming", "district of columbia"
]

US_CITIES = [
    "san francisco", "new york", "seattle", "austin", "boston", "chicago",
    "los angeles", "san jose", "san diego", "denver", "atlanta", "miami",
    "dallas", "houston", "washington", "portland", "pittsburgh", "detroit",
    "minneapolis", "phoenix", "charlotte", "nashville", "salt lake city",
    "philadelphia", "columbus", "raleigh", "durham", "boulder", "cambridge",
    "palo alto", "mountain view", "sunnyvale", "santa clara", "redmond",
    "bellevue", "irvine", "santa monica", "arlington", "mclean", "reston",
    "huntsville", "colorado springs", "ann arbor", "madison", "baltimore",
    "st. louis", "kansas city", "indianapolis", "cincinnati", "tampa"
]
US_CITIES_REGEX = re.compile(r'\b(?:' + '|'.join(re.escape(c) for c in US_CITIES) + r')\b', re.IGNORECASE)

# Unambiguous non-US signals only: full country/region names, or well-known
# foreign cities. Deliberately does NOT include bare 2-letter codes (those are
# handled - and always trusted in favor of a US reading - by the state-token
# step above). Cities like "Tel Aviv" / "Frankfurt" are listed here as a
# fallback for when they show up WITHOUT their colliding state token (e.g.
# "Tel Aviv" alone); if the colliding token IS present ("Tel Aviv, IL") the
# state-token step already returns True before we ever get here.
INTL_PATTERNS = [
    r"\beurope\b", r"\buk\b", r"\bunited kingdom\b", r"\blondon\b",
    r"\bindia\b", r"\bgermany\b", r"\bemea\b", r"\bapac\b", r"\bcanada\b",
    r"\btoronto\b", r"\bireland\b", r"\bsingapore\b", r"\baustralia\b",
    r"\blatam\b", r"\bmexico\b", r"\bbrazil\b",
    r"\btel aviv\b", r"\bchennai\b", r"\bpune\b", r"\bfrankfurt\b",
    r"\bpodgorica\b", r"\blibreville\b", r"\bvientiane\b", r"\bvancouver\b",
    # Additional unambiguous, fully-spelled-out countries (never bare codes,
    # so these can never collide with a US state abbreviation).
    r"\bcosta rica\b", r"\bpanama\b", r"\bcolombia\b", r"\bargentina\b",
    r"\bchile\b", r"\bperu\b", r"\bjapan\b", r"\bchina\b", r"\bspain\b",
    r"\bfrance\b", r"\bitaly\b", r"\bnetherlands\b", r"\bpoland\b",
    r"\bsweden\b", r"\bswitzerland\b", r"\bportugal\b", r"\bnew zealand\b",
    r"\bsouth africa\b", r"\bnigeria\b", r"\begypt\b", r"\bpakistan\b",
    r"\bindonesia\b", r"\bmalaysia\b", r"\bthailand\b", r"\bsouth korea\b",
    r"\bvietnam\b", r"\bphilippines\b", r"\bisrael\b",
]
INTL_REGEX = re.compile("|".join(INTL_PATTERNS), re.IGNORECASE)

US_STATES_SET = {abbr.upper() for abbr in US_STATE_ABBR}
US_TERRITORY_SET = {abbr.upper() for abbr in US_TERRITORY_ABBR}
US_STATES_NAMES_SET = {name.upper() for name in US_STATE_NAMES}
VALID_US_ENDINGS = US_STATES_SET.union(US_TERRITORY_SET).union({"US", "USA", "UNITED STATES"}).union(US_STATES_NAMES_SET)

states_to_strip = US_STATE_ABBR + US_TERRITORY_ABBR + US_STATE_NAMES
STATE_STRIP_REGEX = re.compile(
    r'\b(?:' + '|'.join(re.escape(s) for s in states_to_strip) + r')\b',
    re.IGNORECASE
)


class LocationValidator(ScrapedJobValidator):
    def _do_validate(self, job: ScrapedJob) -> bool:
        if not job.location:
            return False

        loc = job.location.strip()
        if not loc:
            return False

        try:
            # =========================================================
            # 1. EXPLICIT US COUNTRY OVERRIDE (instant pass)
            # Solves: "Anywhere in the US", "New York, NY, USA"
            # =========================================================
            if US_COUNTRY_REGEX.search(loc):
                return True

            # =========================================================
            # 2. STATE TOKEN ANALYSIS (instant pass)
            # Any bare token that exactly matches a US state abbreviation or
            # name is trusted, even if it also happens to be a country code
            # (see policy note above). This runs BEFORE international name
            # checks on purpose: it's the whole point of the recall-first
            # policy.
            # =========================================================
            clean_loc = re.sub(r'(?i)\b(remote|hybrid|onsite|on-site|anywhere|nationwide)\b', '', loc)
            clean_loc = re.sub(r'[()|/;\-]', ',', clean_loc)
            tokens = [t.strip().upper() for t in clean_loc.split(',') if t.strip()]

            if not tokens:
                return False

            if any(t in VALID_US_ENDINGS for t in tokens):
                return True

            # =========================================================
            # 3. NON-US COUNTRY/PROVINCE CODE REJECTION
            # By this point no token matched a US state or territory. A
            # bare 2-letter alphabetic token here (FR, IT, PE, AT, GR, RU,
            # CR, ON, BC, ...) is virtually always a foreign country or
            # province code. Reject on it directly rather than falling
            # through to the curated US city list or GeoText - both of
            # which can be fooled by small same-named US towns (Lima, OH;
            # Vienna, VA; Rome, NY; Moscow, ID; Athens, GA; Paris, TX)
            # into guessing "US" anyway. This adds no false-negative risk:
            # every real US state/territory code is already whitelisted
            # above, so nothing genuinely American is rejected here.
            # =========================================================
            if any(len(t) == 2 and t.isalpha() for t in tokens):
                return False

            # =========================================================
            # 4. UNAMBIGUOUS INTERNATIONAL REJECTION
            # Only reached once we know there's no colliding US state token.
            # Covers spelled-out foreign countries/regions and known foreign
            # cities appearing without their colliding abbreviation.
            # =========================================================
            if INTL_REGEX.search(loc):
                return False

            # =========================================================
            # 5. CURATED US CITY MATCH
            # Runs after step 4 so an explicit foreign country name (or a
            # bare foreign code) always wins over a same-named US city
            # (e.g. "San Jose, Costa Rica" is correctly rejected instead
            # of matching on "San Jose").
            # =========================================================
            if US_CITIES_REGEX.search(loc):
                return True

            # =========================================================
            # 6. GEOTEXT FALLBACK
            # Last-resort safety net for strings our curated lists don't
            # cover. Kept last because GeoText's city/country database is
            # noisy (e.g. it can tag "Ontario" or "Colorado" with unrelated
            # country codes), so we only want it deciding cases nothing
            # else above has an opinion on.
            # =========================================================
            text_for_geotext = STATE_STRIP_REGEX.sub('', loc)
            geo = GeoText(text_for_geotext.title())

            if 'US' in geo.country_mentions:
                return True

            if geo.country_mentions:
                return False

            return False

        except Exception as e:
            print(f"[LocationValidator] Error processing location string: {e}")
            return False