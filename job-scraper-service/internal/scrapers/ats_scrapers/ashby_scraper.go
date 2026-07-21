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

type AshbyScraper struct {
	scraper.BaseScraper
	BaseURL string
}

func NewAshbyScraper(client *http.Client, cfg *config.ScraperConfig) *AshbyScraper {
	return &AshbyScraper{
		BaseScraper: scraper.NewBaseScraper(client, cfg, 250, 250, 250),
		BaseURL:     "https://api.ashbyhq.com/posting-api/job-board/",
	}
}

type AshbyJob struct {
	Title            string `json:"title"`
	JobURL           string `json:"jobUrl"`
	Location         string `json:"location"`
	DescriptionHtml  string `json:"descriptionHtml"`
	DescriptionPlain string `json:"descriptionPlain"`
	PublishedAt      string `json:"publishedAt"`
}

type AshbyResponse struct {
	Jobs []AshbyJob `json:"jobs"`
}

func (a *AshbyScraper) Fetch(ctx context.Context, company string, validationChan chan<- models.ScrapedJob) error {
	a.BaseScraper.Semaphore <- struct{}{}
	defer func() { <-a.BaseScraper.Semaphore }()

	if err := a.BaseScraper.RateLimiter.Wait(ctx); err != nil {
		return err
	}

	url := fmt.Sprintf("%s%s?includeCompensation=true", a.BaseURL, company)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}

	resp, err := a.BaseScraper.Client.Do(req)
	if err != nil {
		log.Printf("[Ashby Fetch] Error for %s: %v", company, err)
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("ashby api error status: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	var ashbyResp AshbyResponse
	if err := json.Unmarshal(body, &ashbyResp); err != nil {
		return err
	}

	for _, rawJob := range ashbyResp.Jobs {
		var postedAt *time.Time
		if rawJob.PublishedAt != "" {
			parsedTime, err := time.Parse(time.RFC3339, rawJob.PublishedAt)
			if err == nil {
				postedAt = &parsedTime
			}
		}

		desc := rawJob.DescriptionHtml
		if desc == "" {
			desc = rawJob.DescriptionPlain
		}

		job := models.ScrapedJob{
			Title:       rawJob.Title,
			Company:     company,
			Platform:    models.Ashby,
			Location:    rawJob.Location,
			Description: desc,
			URL:         rawJob.JobURL,
			PostedAt:    postedAt,
		}
		validationChan <- job
	}

	return nil
}

func (a *AshbyScraper) Enrich(ctx context.Context, job models.ScrapedJob) (models.ScrapedJob, error) {
	return job, nil
}
