package ats_scraper

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"

	"job-scraper-service/internal/config"
	"job-scraper-service/internal/models"
	scraper "job-scraper-service/internal/scrapers"
)

type LeverScraper struct {
	scraper.BaseScraper
	BaseURL string
}

func NewLeverScraper(client *http.Client, cfg *config.ScraperConfig) *LeverScraper {
	return &LeverScraper{
		BaseScraper: scraper.NewBaseScraper(client, cfg, 250, 250, 250),
		BaseURL:     "https://api.lever.co/v0/postings/",
	}
}

type LeverJob struct {
	Text             string `json:"text"`
	HostedURL        string `json:"hostedUrl"`
	CreatedAt        int64  `json:"createdAt"`
	DescriptionPlain string `json:"descriptionPlain"`
	Categories       struct {
		Location string `json:"location"`
	} `json:"categories"`
}

func (l *LeverScraper) Fetch(ctx context.Context, company string, validationChan chan<- models.ScrapedJob) error {
	l.BaseScraper.Semaphore <- struct{}{}
	defer func() { <-l.BaseScraper.Semaphore }()

	if err := l.BaseScraper.RateLimiter.Wait(ctx); err != nil {
		return err
	}

	url := fmt.Sprintf("%s%s?mode=json", l.BaseURL, company)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}

	resp, err := l.BaseScraper.Client.Do(req)
	if err != nil {
		log.Printf("[Lever Fetch] Error for %s: %v", company, err)
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("lever api error status: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	// Lever returns a direct array of objects, not wrapped in a parent struct
	var rawJobs []LeverJob
	if err := json.Unmarshal(body, &rawJobs); err != nil {
		return err
	}

	for _, rawJob := range rawJobs {
		var postedAt *time.Time
		if rawJob.CreatedAt > 0 {
			// Convert Lever's Unix millisecond timestamp to time.Time
			parsedTime := time.UnixMilli(rawJob.CreatedAt)
			postedAt = &parsedTime
		}

		job := models.ScrapedJob{
			Title:       rawJob.Text,
			Company:     company,
			Platform:    models.Lever,
			Location:    rawJob.Categories.Location,
			Description: rawJob.DescriptionPlain,
			URL:         rawJob.HostedURL,
			PostedAt:    postedAt,
		}
		validationChan <- job
	}

	return nil
}

func (l *LeverScraper) Enrich(ctx context.Context, job models.ScrapedJob) (models.ScrapedJob, error) {
	return job, nil
}
