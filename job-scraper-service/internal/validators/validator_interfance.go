package validator

import (
	"fmt"
	"log"
	"sync"

	"job-scraper-service/internal/models"
)

// JobValidator defines a node in the validation chain.
type JobValidator interface {
	Validate(job models.ScrapedJob) bool
	SetNext(validator JobValidator)
	PrintStats(name string)
}

// BaseValidator implements the standard chain traversal and thread-safe stat tracking.
type BaseValidator struct {
	Next JobValidator

	// Thread-safe map for tracking pass/fail metrics across concurrent Goroutines
	mu    sync.Mutex
	stats map[models.JobPlatform]map[string]int
}

func NewBaseValidator() BaseValidator {
	return BaseValidator{
		stats: make(map[models.JobPlatform]map[string]int),
	}
}

func (b *BaseValidator) SetNext(next JobValidator) {
	b.Next = next
}

// PassToNext safely hands the job down the chain if another validator exists.
func (b *BaseValidator) PassToNext(job models.ScrapedJob) bool {
	if b.Next != nil {
		return b.Next.Validate(job)
	}
	return true
}

func (b *BaseValidator) RecordStat(platform models.JobPlatform, status string) {
	b.mu.Lock()
	defer b.mu.Unlock()

	if _, exists := b.stats[platform]; !exists {
		b.stats[platform] = map[string]int{"total": 0, "pass": 0, "fail": 0}
	}
	b.stats[platform][status]++
	b.stats[platform]["total"]++
}

func (b *BaseValidator) PrintStats(name string) {
	func() {
		b.mu.Lock()
		defer b.mu.Unlock()

		for platform, counts := range b.stats {
			log.Printf("[%s] Platform: %s | Scraped: %d | Pass: %d | Fail: %d\n",
				name, platform, counts["total"], counts["pass"], counts["fail"])
		}
	}()

	if b.Next != nil {
		validatorName := fmt.Sprintf("%T", b.Next)
		b.Next.PrintStats(validatorName)
	}
}
