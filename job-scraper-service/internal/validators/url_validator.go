package validator

import (
	"strings"

	"job-scraper-service/internal/models"
)

type URLValidator struct {
	BaseValidator
}

func NewURLValidator() *URLValidator {
	return &URLValidator{
		BaseValidator: NewBaseValidator(),
	}
}

func (v *URLValidator) Validate(job models.ScrapedJob) bool {
	// Must exist and be a valid HTTP web link
	if job.URL == "" || !strings.HasPrefix(job.URL, "http") {
		v.RecordStat(job.Platform, "fail")
		return false
	}

	// Filter out internal ATS test links if any leak through
	lowerURL := strings.ToLower(job.URL)
	if strings.Contains(lowerURL, "test") || strings.Contains(lowerURL, "demo") {
		v.RecordStat(job.Platform, "fail")
		return false
	}

	v.RecordStat(job.Platform, "pass")
	return v.PassToNext(job)
}
