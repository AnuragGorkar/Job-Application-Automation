package validator

import (
	"time"

	"job-scraper-service/internal/models"
)

type TimeWindowValidator struct {
	BaseValidator
}

func NewTimeWindowValidator() *TimeWindowValidator {
	return &TimeWindowValidator{
		BaseValidator: NewBaseValidator(),
	}
}

func (v *TimeWindowValidator) Validate(job models.ScrapedJob) bool {
	// Since PostedAt is a pointer (*time.Time), check for nil to avoid panics
	if job.PostedAt == nil {
		v.RecordStat(job.Platform, "fail")
		return false
	}

	// Dereference the pointer to get the time.Time value and convert to UTC
	jobTime := (*job.PostedAt).UTC()

	if time.Since(jobTime) > 24*time.Hour {
		v.RecordStat(job.Platform, "fail")
		return false
	}

	v.RecordStat(job.Platform, "pass")
	return v.PassToNext(job)
}
