package validator

import (
	"job-scraper-service/internal/models"
)

type WrapperValidator struct {
	BaseValidator
}

func NewWrapperValidator() *WrapperValidator {
	return &WrapperValidator{
		BaseValidator: NewBaseValidator(),
	}
}

func (v *WrapperValidator) Validate(job models.ScrapedJob) bool {
	v.RecordStat(job.Platform, "pass")
	return v.PassToNext(job)
}
