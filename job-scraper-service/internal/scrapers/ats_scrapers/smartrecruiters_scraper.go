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

type SmartRecruitersScraper struct {
	scraper.BaseScraper
	BaseURL string
}

func NewSmartRecruitersScraper(client *http.Client, cfg *config.ScraperConfig) *SmartRecruitersScraper {
	return &SmartRecruitersScraper{
		// More restrictive rate limit (4 max concurrent) to prevent SR WAF blocks
		BaseScraper: scraper.NewBaseScraper(client, cfg, 100, 100, 100),
		BaseURL:     "https://api.smartrecruiters.com/v1/companies/",
	}
}

type SmartRecruitersJob struct {
	Name         string `json:"name"`
	Ref          string `json:"ref"`
	ReleasedDate string `json:"releasedDate"`
	Location     struct {
		City string `json:"city"`
	} `json:"location"`
	JobAd struct {
		Sections interface{} `json:"sections"`
	} `json:"jobAd"`
}

type SmartRecruitersResponse struct {
	Content []SmartRecruitersJob `json:"content"`
}

func (s *SmartRecruitersScraper) Fetch(ctx context.Context, company string, validationChan chan<- models.ScrapedJob) error {
	s.BaseScraper.Semaphore <- struct{}{}
	defer func() { <-s.BaseScraper.Semaphore }()

	if err := s.BaseScraper.RateLimiter.Wait(ctx); err != nil {
		return err
	}

	url := fmt.Sprintf("%s%s/postings", s.BaseURL, company)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}

	resp, err := s.BaseScraper.Client.Do(req)
	if err != nil {
		log.Printf("[Smart Recruiters Fetch] Error for %s: %v", company, err)
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("smartrecruiters api error status: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}

	var srResp SmartRecruitersResponse
	if err := json.Unmarshal(body, &srResp); err != nil {
		return err
	}

	for _, rawJob := range srResp.Content {
		var postedAt *time.Time
		if rawJob.ReleasedDate != "" {
			parsedTime, err := time.Parse(time.RFC3339, rawJob.ReleasedDate)
			if err == nil {
				postedAt = &parsedTime
			}
		}

		// Flatten the varied sections structure into a parseable string
		var rawDesc string
		if rawJob.JobAd.Sections != nil {
			bytes, _ := json.Marshal(rawJob.JobAd.Sections)
			rawDesc = string(bytes)
		}

		job := models.ScrapedJob{
			Title:       rawJob.Name,
			Company:     company,
			Platform:    models.SmartRecruiters,
			Location:    rawJob.Location.City,
			Description: rawDesc,
			URL:         rawJob.Ref,
			PostedAt:    postedAt,
		}
		validationChan <- job
	}

	return nil
}

func (s *SmartRecruitersScraper) Enrich(ctx context.Context, job models.ScrapedJob) (models.ScrapedJob, error) {
	return job, nil
}
