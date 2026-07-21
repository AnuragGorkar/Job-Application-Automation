package validator

import (
	"regexp"
	"strings"
	"unicode"

	"job-scraper-service/internal/models"
)

type LocationValidator struct {
	BaseValidator
	usCountryRegex *regexp.Regexp
	usCitiesRegex  *regexp.Regexp
	intlRegex      *regexp.Regexp
	cleanLocRegex  *regexp.Regexp
	punctRegex     *regexp.Regexp
	validUSEndings map[string]bool
}

func NewLocationValidator() *LocationValidator {
	// ==========================================
	// CONSTANTS & PATTERNS
	// ==========================================
	usCountryPatterns := []string{`\bunited states\b`, `\bu\.s\.a?\.?\b`, `\busa\b`, `\bus\b`}

	usStateAbbr := []string{
		"al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in",
		"ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv",
		"nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn",
		"tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
	}

	usTerritoryAbbr := []string{"pr", "gu", "vi", "as", "mp"}

	usStateNames := []string{
		"alabama", "alaska", "arizona", "arkansas", "california", "colorado",
		"connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
		"illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
		"maryland", "massachusetts", "michigan", "minnesota", "mississippi",
		"missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
		"new mexico", "new york", "north carolina", "north dakota", "ohio",
		"oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
		"south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
		"washington", "west virginia", "wisconsin", "wyoming", "district of columbia",
	}

	usCities := []string{
		"san francisco", "new york", "seattle", "austin", "boston", "chicago",
		"los angeles", "san jose", "san diego", "denver", "atlanta", "miami",
		"dallas", "houston", "washington", "portland", "pittsburgh", "detroit",
		"minneapolis", "phoenix", "charlotte", "nashville", "salt lake city",
		"philadelphia", "columbus", "raleigh", "durham", "boulder", "cambridge",
		"palo alto", "mountain view", "sunnyvale", "santa clara", "redmond",
		"bellevue", "irvine", "santa monica", "arlington", "mclean", "reston",
		"huntsville", "colorado springs", "ann arbor", "madison", "baltimore",
		"st. louis", "kansas city", "indianapolis", "cincinnati", "tampa",
	}

	intlPatterns := []string{
		`\beurope\b`, `\buk\b`, `\bunited kingdom\b`, `\blondon\b`,
		`\bindia\b`, `\bgermany\b`, `\bemea\b`, `\bapac\b`, `\bcanada\b`,
		`\btoronto\b`, `\bireland\b`, `\bsingapore\b`, `\baustralia\b`,
		`\blatam\b`, `\bmexico\b`, `\bbrazil\b`,
		`\btel aviv\b`, `\bchennai\b`, `\bpune\b`, `\bfrankfurt\b`,
		`\bpodgorica\b`, `\blibreville\b`, `\bvientiane\b`, `\bvancouver\b`,
		`\bcosta rica\b`, `\bpanama\b`, `\bcolombia\b`, `\bargentina\b`,
		`\bchile\b`, `\bperu\b`, `\bjapan\b`, `\bchina\b`, `\bspain\b`,
		`\bfrance\b`, `\bitaly\b`, `\bnetherlands\b`, `\bpoland\b`,
		`\bsweden\b`, `\bswitzerland\b`, `\bportugal\b`, `\bnew zealand\b`,
		`\bsouth africa\b`, `\bnigeria\b`, `\begypt\b`, `\bpakistan\b`,
		`\bindonesia\b`, `\bmalaysia\b`, `\bthailand\b`, `\bsouth korea\b`,
		`\bvietnam\b`, `\bphilippines\b`, `\bisrael\b`,
	}

	// Build the valid US endings map (O(1) lookups)
	validUSEndings := make(map[string]bool)
	for _, abbr := range usStateAbbr {
		validUSEndings[strings.ToUpper(abbr)] = true
	}
	for _, abbr := range usTerritoryAbbr {
		validUSEndings[strings.ToUpper(abbr)] = true
	}
	for _, name := range usStateNames {
		validUSEndings[strings.ToUpper(name)] = true
	}
	validUSEndings["US"] = true
	validUSEndings["USA"] = true
	validUSEndings["UNITED STATES"] = true

	// Compile Regexes
	usCitiesPattern := `\b(?:` + strings.Join(escapeStrings(usCities), `|`) + `)\b`

	return &LocationValidator{
		BaseValidator:  NewBaseValidator(),
		usCountryRegex: regexp.MustCompile(`(?i)` + strings.Join(usCountryPatterns, `|`)),
		usCitiesRegex:  regexp.MustCompile(`(?i)` + usCitiesPattern),
		intlRegex:      regexp.MustCompile(`(?i)` + strings.Join(intlPatterns, `|`)),
		cleanLocRegex:  regexp.MustCompile(`(?i)\b(remote|hybrid|onsite|on-site|anywhere|nationwide)\b`),
		punctRegex:     regexp.MustCompile(`[()|/;\-]`),
		validUSEndings: validUSEndings,
	}
}

func (v *LocationValidator) Validate(job models.ScrapedJob) bool {
	if job.Location == "" {
		v.RecordStat(job.Platform, "fail")
		return false
	}

	loc := strings.TrimSpace(job.Location)
	if loc == "" {
		v.RecordStat(job.Platform, "fail")
		return false
	}

	// 1. EXPLICIT US COUNTRY OVERRIDE
	if v.usCountryRegex.MatchString(loc) {
		v.RecordStat(job.Platform, "pass")
		return v.PassToNext(job)
	}

	// 2. STATE TOKEN ANALYSIS
	cleanLoc := v.cleanLocRegex.ReplaceAllString(loc, "")
	cleanLoc = v.punctRegex.ReplaceAllString(cleanLoc, ",")

	rawTokens := strings.Split(cleanLoc, ",")
	var tokens []string
	for _, t := range rawTokens {
		trimmed := strings.ToUpper(strings.TrimSpace(t))
		if trimmed != "" {
			tokens = append(tokens, trimmed)
		}
	}

	if len(tokens) == 0 {
		v.RecordStat(job.Platform, "fail")
		return false
	}

	for _, t := range tokens {
		if v.validUSEndings[t] {
			v.RecordStat(job.Platform, "pass")
			return v.PassToNext(job)
		}
	}

	// 3. NON-US COUNTRY/PROVINCE CODE REJECTION
	for _, t := range tokens {
		if len(t) == 2 && isAlpha(t) {
			v.RecordStat(job.Platform, "fail")
			return false
		}
	}

	// 4. UNAMBIGUOUS INTERNATIONAL REJECTION
	if v.intlRegex.MatchString(loc) {
		v.RecordStat(job.Platform, "fail")
		return false
	}

	// 5. CURATED US CITY MATCH
	if v.usCitiesRegex.MatchString(loc) {
		v.RecordStat(job.Platform, "pass")
		return v.PassToNext(job)
	}

	// 6. GEOTEXT FALLBACK
	// Note: Omitted in Go as there is no direct equivalent to Python's GeoText.
	// Falling back to returning false for unrecognized locations.

	v.RecordStat(job.Platform, "fail")
	return false
}

// Helper function to escape strings for regex
func escapeStrings(strs []string) []string {
	escaped := make([]string, len(strs))
	for i, s := range strs {
		escaped[i] = regexp.QuoteMeta(s)
	}
	return escaped
}

// Helper function to check if a string contains only letters
func isAlpha(s string) bool {
	for _, r := range s {
		if !unicode.IsLetter(r) {
			return false
		}
	}
	return true
}
