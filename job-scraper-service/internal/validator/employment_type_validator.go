package validator

import (
	"regexp"
	"strings"

	"job-scraper-service/internal/models"
)

type EmploymentTypeValidator struct {
	BaseValidator
	exclusionRegex *regexp.Regexp
}

func NewEmploymentTypeValidator() *EmploymentTypeValidator {
	patterns := []string{
		`\bintern\b`, `\binternship\b`, `\bco-op\b`,
		`\bcontract\b`, `\bcontractor\b`, `\bpart-time\b`, `\bstudent\b`,
	}
	return &EmploymentTypeValidator{
		BaseValidator:  NewBaseValidator(),
		exclusionRegex: regexp.MustCompile("(?i)" + strings.Join(patterns, "|")),
	}
}

func (e *EmploymentTypeValidator) Validate(job models.ScrapedJob) bool {
	if job.Title != "" && e.exclusionRegex.MatchString(job.Title) {
		e.RecordStat(job.Platform, "fail")
		return false
	}
	e.RecordStat(job.Platform, "pass")
	return e.PassToNext(job)
}
