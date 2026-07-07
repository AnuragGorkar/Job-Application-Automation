import pytest
from app.schemas.scraped_job import ScrapedJob
from app.services.job_scrapers.validators.location_validator import LocationValidator

# Instantiate the validator once for the test module
validator = LocationValidator()

def validate(location_string: str) -> bool:
    """Helper function to keep tests clean."""
    job = ScrapedJob.model_construct(location=location_string)
    return validator._do_validate(job)

# ==========================================
# TEST SUITES: STANDARD US LOCATIONS
# ==========================================

@pytest.mark.parametrize("location", [
    "San Francisco, CA",
    "Chicago, IL",
    "Austin, TX",
    "New York, NY",
    "Evanston, IL",
    "Kalamazoo, MI",
    "Round Rock, TX",
    "San Jose, CA, USA",
    "Seattle, WA, United States",
    "United States",
    "USA",
    "San Francisco",
    "New York",
    "Chicago",
    "Salt Lake City, UT",
    "Winston-Salem, NC",
    "Washington D.C.",
    "Washington, DC",
    "Austin, Texas",
    "Chicago, Illinois",
    "Denver, Colorado"
])
def test_valid_us_locations(location):
    """Ensure standard and structurally sound US locations pass."""
    assert validate(location) is True


# ==========================================
# TEST SUITES: INTERNATIONAL EXCLUSIONS
# (deduplicated - the original file defined this test twice under the same
#  name, which meant pytest silently dropped the first copy and its cases,
#  including "San Jose, Costa Rica" / "San Jose, CR", ever ran.)
# ==========================================

@pytest.mark.parametrize("location", [
    "London, UK",
    "Berlin, Germany",
    "Toronto, Canada",
    "Sydney, Australia",
    "Paris, EMEA",
    "Paris, FR",
    "Tokyo, JP",
    "Madrid, ES",
    "Bangalore, India",
    "Dublin, Ireland",
    "Sao Paulo, Brazil",
    "São Paulo, Brazil",
    "London, Ontario",
    "Remote - LATAM",
    "APAC Region",
    # A same-named US city loses to an explicit, non-colliding foreign
    # marker - whether it's a fully spelled-out country name or a bare
    # 2-letter code that isn't also a US state/territory abbreviation.
    "San Jose, Costa Rica",
    "San Jose, CR",
    "Paris, FR",
    "Tokyo, JP",
    "Madrid, ES",
    "Rome, IT",
    "Lima, PE",
    "Vienna, AT",
    "Athens, GR",
    "Moscow, RU",
])
def test_invalid_international_locations(location):
    """Ensure clearly international locations are rejected."""
    assert validate(location) is False


# ==========================================
# TEST SUITE: US STATE / COUNTRY-CODE COLLISIONS
# Because we prioritize zero false negatives for US jobs, any bare token
# that matches a US state abbreviation is trusted, even when the same two
# letters are also a real country code and the city named is a known
# foreign city. This is an intentional, accepted trade-off, not a bug.
# ==========================================

@pytest.mark.parametrize("location", [
    "Tel Aviv, IL",       # IL also matches Israel
    "Chennai, IN",        # IN also matches India
    "Pune, PA",           # PA also matches Panama
    "Toronto, CA",        # CA also matches Canada
    "Frankfurt, DE",      # DE also matches Germany
    "Podgorica, ME",      # ME also matches Montenegro
    "Libreville, GA",     # GA also matches Gabon
    "Vientiane, LA",      # LA also matches Laos
    "IL, Tel Aviv",
    "IN, TN, Chennai",
    "CA, Vancouver",
    "Hybrid (Tel Aviv, IL)",
    "Tel Aviv, IL, USA",
    "Chennai, IN, United States",
    "Frankfurt, DE, USA",
    "Jakarta, ID",        # ID also matches Idaho
    "Bogota, CO",         # CO also matches Colorado
    "Buenos Aires, AR",   # AR also matches Arkansas
    "Casablanca, MA",     # MA also matches Massachusetts
])
def test_state_abbreviation_collisions_are_accepted(location):
    """
    Known collisions (DE=Germany/Delaware, IL=Israel/Illinois, etc.).
    We accept these to guarantee 100% recall on real US postings.
    """
    assert validate(location) is True


@pytest.mark.parametrize("location", [
    "San Juan, PR",
    "Tamuning, GU",
    "Charlotte Amalie, VI",
    "Pago Pago, AS",
    "Saipan, MP",
])
def test_us_territories_are_accepted(location):
    """US territory codes must not be swept up by the foreign 2-letter code rule."""
    assert validate(location) is True


@pytest.mark.parametrize("location", [
    # Same foreign cities as above, but WITHOUT a colliding state token -
    # nothing here suggests a US reading at all, so these are rejected.
    "Tel Aviv",
    "Chennai",
    "Frankfurt",
])
def test_foreign_city_without_state_token_is_rejected(location):
    assert validate(location) is False


# ==========================================
# TEST SUITES: NOISE & FORMATTING
# ==========================================

@pytest.mark.parametrize("location, expected", [
    ("Remote, Chicago, IL", True),
    ("Hybrid - Austin, TX", True),
    ("On-site, Seattle, WA", True),
    ("San Diego, CA (On-site)", True),
    ("New York, NY (Hybrid)", True),
    ("(Remote) Denver, CO", True),
    ("San Francisco (CA)", True),
    ("  seattle , wa  ", True),
    ("boston,MA", True),
    ("MIAMI , FL", True),
    ("Remote / Chicago, IL", True),
    ("New York | NY", True),
    ("Remote, London, UK", False),
    ("Remote / Bangalore, India", False),
])
def test_noisy_formatting(location, expected):
    """Ensure the validator correctly cleans job-board specific noise before checking."""
    assert validate(location) is expected


# ==========================================
# TEST SUITES: NULL & EDGE STATES
# ==========================================

@pytest.mark.parametrize("location", [
    "",
    "   ",
    None,
    "12345",
    "Remote",
    "Hybrid",
    "Anywhere",
    "Earth",
])
def test_empty_or_vague_locations(location):
    """Ensure missing or overly vague locations fail safely."""
    assert validate(location) is False


@pytest.mark.parametrize("location", [
    "San Francisco, CA", "San Jose, CA", "Palo Alto, CA", "Mountain View, CA",
    "Sunnyvale, CA", "Santa Clara, CA", "Seattle, WA", "Redmond, WA", "Bellevue, WA",
    "New York, NY", "Austin, TX", "Boston, MA", "Cambridge, MA",
    "Chicago, IL", "Los Angeles, CA", "San Diego, CA", "Denver, CO", "Boulder, CO",
    "Atlanta, GA", "Miami, FL", "Dallas, TX", "Houston, TX", "Washington, DC",
    "Arlington, VA", "McLean, VA", "Reston, VA", "Portland, OR", "Pittsburgh, PA",
    "Detroit, MI", "Minneapolis, MN", "Phoenix, AZ", "Charlotte, NC", "Nashville, TN",
    "Salt Lake City, UT", "Philadelphia, PA", "Columbus, OH", "Raleigh, NC", "Durham, NC",
    "Huntsville, AL", "Colorado Springs, CO", "Ann Arbor, MI", "Madison, WI",
    "Baltimore, MD", "St. Louis, MO", "Kansas City, MO", "Indianapolis, IN", "Tampa, FL"
])
def test_top_tech_hubs_abbreviations(location):
    """Ensure every major US tech hub passes with standard abbreviations."""
    assert validate(location) is True


@pytest.mark.parametrize("location", [
    "Austin, Texas",
    "Denver, Colorado",
    "Chicago, Illinois",
    "Seattle, Washington",
    "Atlanta, Georgia",
    "Raleigh, North Carolina",
    "Salt Lake City, Utah",
    "Miami, Florida"
])
def test_full_state_names(location):
    """Ensure spelled out states do not get dropped."""
    assert validate(location) is True


@pytest.mark.parametrize("location", [
    "United States",
    "USA",
    "Anywhere in the US",
    "Remote, USA",
    "Nationwide, United States"
])
def test_explicit_country_markers(location):
    """Ensure explicit generic US mentions pass."""
    assert validate(location) is True


@pytest.mark.parametrize("location", [
    "San Francisco, CA (Remote)",
    "(Hybrid) New York, NY",
    "Austin, TX - Onsite",
    "Seattle, WA | Remote",
    "Boston, MA / New York, NY",
    "San Francisco, CA; Austin, TX",
    "Remote (CA, WA, NY, TX)",
    "New York, NY / London, UK"  # Dual location hiring in the US
])
def test_noisy_us_formats(location):
    """Ensure job board noise and multiple locations do not cause false negatives."""
    assert validate(location) is True


@pytest.mark.parametrize("location", [
    # Because we prioritize zero false negatives for US jobs, we intentionally
    # allow token collisions to pass rather than risk dropping jobs in
    # Delaware or Illinois.
    "Frankfurt, DE",
    "Tel Aviv, IL",
    "Chennai, IN"
])
def test_acceptable_false_positives(location):
    """
    Known collisions (DE=Germany/Delaware, IL=Israel/Illinois).
    Because we prioritize 100% US recall, we expect these to pass (True).
    """
    assert validate(location) is True