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

type GreenhouseScraper struct {
	scraper.BaseScraper
	BaseURL string
}

func NewGreenhouseScraper(client *http.Client, cfg *config.ScraperConfig) *GreenhouseScraper {
	return &GreenhouseScraper{
		// BaseScraper: scraper.NewBaseScraper(client, cfg, 100, 50, 100), Safe config
		BaseScraper: scraper.NewBaseScraper(client, cfg, 250, 250, 250), // 50 concurrent requests max
		BaseURL:     "https://boards-api.greenhouse.io/v1/boards/",
	}
}

// GreenhouseJob matches the internal JSON fields returned by the Greenhouse API.
type GreenhouseJob struct {
	Title       string `json:"title"`
	AbsoluteURL string `json:"absolute_url"`
	UpdatedAt   string `json:"updated_at"`
	Location    struct {
		Name string `json:"name"`
	} `json:"location"`
	Content string `json:"content"`
}

type GreenhouseResponse struct {
	Jobs []GreenhouseJob `json:"jobs"`
}

func (g *GreenhouseScraper) Fetch(ctx context.Context, company string, validationChan chan<- models.ScrapedJob) error {
	// 1. Concurrency gate: Acquire structural semaphore block
	g.BaseScraper.Semaphore <- struct{}{}
	defer func() { <-g.BaseScraper.Semaphore }()

	// 2. Token bucket protection rate check
	if err := g.BaseScraper.RateLimiter.Wait(ctx); err != nil {
		return err
	}

	url := fmt.Sprintf("%s%s/jobs?content=true", g.BaseURL, company)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}

	resp, err := g.BaseScraper.Client.Do(req)
	if err != nil {
		log.Printf("[Greenhouse Fetch] Error for %s: %v", company, err)
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("greenhouse api error status: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	var ghResp GreenhouseResponse
	if err := json.Unmarshal(body, &ghResp); err != nil {
		return err
	}

	// 3. Transform and stream jobs immediately into the pipeline channel
	for _, rawJob := range ghResp.Jobs {
		// 1. Initialize a nil pointer for the time
		var postedAt *time.Time

		// 2. Safely attempt to parse the string if it isn't empty
		if rawJob.UpdatedAt != "" {
			parsedTime, err := time.Parse(time.RFC3339, rawJob.UpdatedAt)
			if err == nil {
				// If successful, assign the memory address of the parsed time
				postedAt = &parsedTime
			} else {
				// Log the error but don't crash the scraper; it will just remain nil
				log.Printf("Warning: Failed to parse time '%s' for job %s", rawJob.UpdatedAt, rawJob.Title)
			}
		}

		job := models.ScrapedJob{
			Title:       rawJob.Title,
			Company:     company,
			Platform:    models.Greenhouse,
			Location:    rawJob.Location.Name,
			Description: rawJob.Content,
			URL:         rawJob.AbsoluteURL,
			PostedAt:    postedAt,
		}
		validationChan <- job
	}

	return nil
}

func (g *GreenhouseScraper) Enrich(ctx context.Context, job models.ScrapedJob) (models.ScrapedJob, error) {
	// Greenhouse provides full content in Phase 1, no deep enrichment needed.
	return job, nil
}
