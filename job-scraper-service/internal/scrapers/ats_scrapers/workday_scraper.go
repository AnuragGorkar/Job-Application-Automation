package ats_scraper

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os" // <-- Added to read the file
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"job-scraper-service/internal/config"
	"job-scraper-service/internal/models"
	scraper "job-scraper-service/internal/scrapers"
)

// WorkdayCompanyConfig matches the structure of your JSON values
type WorkdayCompanyConfig struct {
	APIURL   string `json:"api_url"`
	Tenant   string `json:"tenant"`
	Server   string `json:"server"`
	PortalID string `json:"portal_id"`
}

type WorkdayScraper struct {
	scraper.BaseScraper
	dateRegex *regexp.Regexp
	configs   map[string]WorkdayCompanyConfig
}

func NewWorkdayScraper(client *http.Client, cfg *config.ScraperConfig) *WorkdayScraper {
	// 1. Read the file dynamically from your root assets folder
	fileBytes, err := os.ReadFile("assets/workday_companies_config.json")
	if err != nil {
		log.Fatalf("Failed to read Workday config file from assets: %v", err)
	}

	// 2. Parse the JSON into the map
	var loadedConfigs map[string]WorkdayCompanyConfig
	if err := json.Unmarshal(fileBytes, &loadedConfigs); err != nil {
		log.Fatalf("Failed to parse Workday config JSON: %v", err)
	}

	return &WorkdayScraper{
		// Strict WAF token bucket: 5 req/s max. Semaphore at 10 concurrent companies.
		BaseScraper: scraper.NewBaseScraper(client, cfg, 10, 10, 50),
		dateRegex:   regexp.MustCompile(`(\d+)`),
		configs:     loadedConfigs,
	}
}

type WorkdayPayload struct {
	AppliedFacets map[string]interface{} `json:"appliedFacets"`
	Limit         int                    `json:"limit"`
	Offset        int                    `json:"offset"`
	SearchText    string                 `json:"searchText"`
}

type WorkdayResponse struct {
	JobPostings []struct {
		Title         string `json:"title"`
		ExternalPath  string `json:"externalPath"`
		LocationsText string `json:"locationsText"`
		PostedOn      string `json:"postedOn"`
	} `json:"jobPostings"`
	Total int `json:"total"`
}

func (w *WorkdayScraper) _parseWorkdayDate(postedOn string) *time.Time {
	now := time.Now().UTC()
	if postedOn == "" {
		return &now
	}

	text := strings.ToLower(postedOn)
	var t time.Time

	if strings.Contains(text, "today") {
		t = now
	} else if strings.Contains(text, "yesterday") {
		t = now.AddDate(0, 0, -1)
	} else {
		match := w.dateRegex.FindStringSubmatch(text)
		if len(match) > 1 {
			days, _ := strconv.Atoi(match[1])
			t = now.AddDate(0, 0, -days)
		} else {
			t = now
		}
	}
	return &t
}

// Fetch acts as the Workday Orchestrator, completely ignoring the dummy target
// string and looping over the embedded JSON map instead.
func (w *WorkdayScraper) Fetch(ctx context.Context, dummyTarget string, validationChan chan<- models.ScrapedJob) error {
	if len(w.configs) == 0 {
		log.Println("No Workday configurations loaded. Aborting.")
		return nil
	}

	log.Printf("Starting Workday Orchestrator for %d companies...", len(w.configs))
	var wg sync.WaitGroup

	for companyName, cfg := range w.configs {
		wg.Add(1)

		// Spin up a separate Goroutine for every Workday company
		go func(name string, configData WorkdayCompanyConfig) {
			defer wg.Done()
			w.scrapeSingleCompany(ctx, name, configData, validationChan)
		}(companyName, cfg)
	}

	wg.Wait()
	log.Println("Workday Orchestrator finished.")
	return nil
}

// scrapeSingleCompany handles the pagination and network retries for an individual company
func (w *WorkdayScraper) scrapeSingleCompany(ctx context.Context, companyName string, cfg WorkdayCompanyConfig, validationChan chan<- models.ScrapedJob) {
	// SEMAPHORE APPLIED HERE: Restricts how many Workday companies paginate simultaneously
	w.BaseScraper.Semaphore <- struct{}{}
	defer func() { <-w.BaseScraper.Semaphore }()

	offset := 0
	limit := 20
	totalJobs := 1

	for offset < totalJobs {
		// Apply token bucket rate limiter to prevent WAF blocks
		if err := w.BaseScraper.RateLimiter.Wait(ctx); err != nil {
			return
		}

		payload := WorkdayPayload{
			AppliedFacets: make(map[string]interface{}),
			Limit:         limit,
			Offset:        offset,
			SearchText:    "",
		}

		jsonPayload, _ := json.Marshal(payload)
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, cfg.APIURL, bytes.NewBuffer(jsonPayload))
		if err != nil {
			return
		}

		req.Header.Set("Accept", "application/json")
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

		resp, err := w.BaseScraper.Client.Do(req)
		if err != nil {
			log.Printf("[Workday Fetch] Error for %s: %v", companyName, err)
			return
		}

		if resp.StatusCode != http.StatusOK {
			resp.Body.Close()
			log.Printf("Workday pagination error status %d for %s", resp.StatusCode, companyName)
			break
		}

		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		var wdResp WorkdayResponse
		if err := json.Unmarshal(body, &wdResp); err != nil {
			break
		}

		totalJobs = wdResp.Total
		if len(wdResp.JobPostings) == 0 {
			break
		}

		// Use the JSON data or fallback to reasonable defaults
		tenant := cfg.Tenant
		if tenant == "" {
			tenant = companyName
		}
		server := cfg.Server
		if server == "" {
			server = "wd1"
		}
		portalID := cfg.PortalID
		if portalID == "" {
			portalID = "External"
		}

		for _, rawJob := range wdResp.JobPostings {
			publicURL := ""
			if rawJob.ExternalPath != "" {
				publicURL = fmt.Sprintf("https://%s.%s.myworkdayjobs.com/en-US/%s%s", tenant, server, portalID, rawJob.ExternalPath)
			}

			job := models.ScrapedJob{
				Title:    rawJob.Title,
				Company:  companyName, // Keep tracking the original key
				Platform: models.Workday,
				Location: rawJob.LocationsText,
				URL:      publicURL,
				PostedAt: w._parseWorkdayDate(rawJob.PostedOn),
			}
			validationChan <- job
		}

		offset += limit
		time.Sleep(500 * time.Millisecond) // Polite pause between successful pages
	}
}

func (w *WorkdayScraper) Enrich(ctx context.Context, job models.ScrapedJob) (models.ScrapedJob, error) {
	if err := w.BaseScraper.RateLimiter.Wait(ctx); err != nil {
		return job, err
	}

	// 1. Look up the specific tenant from the embedded config map
	cfg, exists := w.configs[job.Company]
	tenant := job.Company
	if exists && cfg.Tenant != "" {
		tenant = cfg.Tenant
	}

	// 2. Convert the public HTML URL into the backend API URL
	cxsURL := strings.Replace(job.URL, "/en-US/", fmt.Sprintf("/wday/cxs/%s/", tenant), 1)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, cxsURL, nil)
	if err != nil {
		return job, err
	}

	req.Header.Set("Accept", "application/json")
	req.Header.Set("Accept-Language", "en-US")
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

	resp, err := w.BaseScraper.Client.Do(req)
	if err != nil {
		return job, err
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		var detailData map[string]interface{}
		if err := json.NewDecoder(resp.Body).Decode(&detailData); err == nil {
			if info, ok := detailData["jobPostingInfo"].(map[string]interface{}); ok {
				if desc, ok := info["jobDescription"].(string); ok {
					job.Description = desc
				}
			}
		}
	} else {
		log.Printf("[Enricher] Workday detail fetch failed (%d) for %s", resp.StatusCode, cxsURL)
	}

	return job, nil
}
