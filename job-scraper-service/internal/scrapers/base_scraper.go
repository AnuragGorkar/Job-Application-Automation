package scraper

import (
	"context"
	"net/http"

	"job-scraper-service/internal/config"
	"job-scraper-service/internal/models"

	"golang.org/x/time/rate"
)

type Scraper interface {
	// Fetch pushes jobs into the validation pipeline.
	Fetch(ctx context.Context, company string, validationChan chan<- models.ScrapedJob) error

	// Enrich takes a valid job, fetches deeper details, and returns the updated job.
	Enrich(ctx context.Context, job models.ScrapedJob) (models.ScrapedJob, error)
}

// BaseScraper holds the shared network infrastructure.
type BaseScraper struct {
	Client      *http.Client
	Config      *config.ScraperConfig
	RateLimiter *rate.Limiter
	Semaphore   chan struct{} // Acts as the concurrency gate for the specific ATS
}

// NewBaseScraper initializes the common infrastructure.
func NewBaseScraper(client *http.Client, cfg *config.ScraperConfig, limit rate.Limit, burst int, maxConcurrent int) BaseScraper {
	return BaseScraper{
		Client:      client,
		Config:      cfg,
		RateLimiter: rate.NewLimiter(limit, burst),
		Semaphore:   make(chan struct{}, maxConcurrent),
	}
}
