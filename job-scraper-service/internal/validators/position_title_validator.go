package validator

import (
	"regexp"
	"strings"

	"job-scraper-service/internal/models"
)

type PositionTitleValidator struct {
	BaseValidator
	roleRegex      *regexp.Regexp
	seniorityRegex *regexp.Regexp
}

func NewPositionTitleValidator() *PositionTitleValidator {
	rolePatterns := []string{
		`\bsoftware engineer\b`, `\bsoftware developer\b`, `\bsde\b`,
		`\bbackend engineer\b`, `\bback[- ]end engineer\b`,
		`\bfull[- ]stack engineer\b`, `\bapplication engineer\b`,
		`\bmachine learning engineer\b`, `\bml engineer\b`, `\bmle\b`,
		`\bdata scientist\b`, `\bdata science\b`, `\bapplied scientist\b`,
		`\bai engineer\b`, `\bgenai engineer\b`, `\bllm engineer\b`,
	}

	seniorityPatterns := []string{
		`\bsenior\b`, `\bsr\.?\b`, `\blead\b`, `\bstaff\b`, `\bprincipal\b`,
		`\bmanager\b`, `\bdirector\b`, `\barchitect\b`,
	}

	return &PositionTitleValidator{
		BaseValidator:  NewBaseValidator(),
		roleRegex:      regexp.MustCompile("(?i)" + strings.Join(rolePatterns, "|")),
		seniorityRegex: regexp.MustCompile("(?i)" + strings.Join(seniorityPatterns, "|")),
	}
}

func (p *PositionTitleValidator) Validate(job models.ScrapedJob) bool {
	if job.Title == "" {
		p.RecordStat(job.Platform, "fail")
		return false
	}

	// 1. Exclude high-level management and seniority items
	if p.seniorityRegex.MatchString(job.Title) {
		p.RecordStat(job.Platform, "fail")
		return false
	}

	// 2. Validate structural target matches
	if !p.roleRegex.MatchString(job.Title) {
		p.RecordStat(job.Platform, "fail")
		return false
	}

	p.RecordStat(job.Platform, "pass")
	return p.PassToNext(job)
}
