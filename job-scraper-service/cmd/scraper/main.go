package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"sync"
	"time"

	"job-scraper-service/internal/config"
	"job-scraper-service/internal/models"
	scraper "job-scraper-service/internal/scrapers"
	ats_scraper "job-scraper-service/internal/scrapers/ats_scrapers"
	validator "job-scraper-service/internal/validators"
)

// getScrapers functions exactly like build_scraper_dict in Python,
// instantiating the scraping drivers based on active platform keys.
func getScrapers(sharedClient *http.Client, cfg *config.ScraperConfig) map[models.JobPlatform]scraper.Scraper {
	scrapersMap := make(map[models.JobPlatform]scraper.Scraper)

	// Register drivers using their dedicated platform enums
	scrapersMap[models.Greenhouse] = ats_scraper.NewGreenhouseScraper(sharedClient, cfg)
	// scrapersMap[models.Workday] = ats_scraper.NewWorkdayScraper(sharedClient, cfg)
	// scrapersMap[models.Lever] = ats_scraper.NewLeverScraper(sharedClient, cfg)

	return scrapersMap
}

func main() {
	// 1. Initialize configuration and structural shared dependencies
	sharedClient := &http.Client{
		Timeout: 30 * time.Second,
	}
	cfg := config.DefaultConfig()

	// 2. Initialize active platform scrapers map
	scrapersMap := getScrapers(sharedClient, cfg)

	// 3. Pull the master data-driven company targets configuration map
	companiesDict := config.GetCompanies() // Expected type: map[models.JobPlatform][]string

	// 4. Initialize validation engine chain
	vChain := validator.BuildChain()

	// 5. Create communication channels (Conveyor belts)
	validationChan := make(chan models.ScrapedJob, 500)
	enrichmentChan := make(chan models.ScrapedJob, 500)
	finalResults := make([]models.ScrapedJob, 0)

	// Synchronization primitives
	var resultsMu sync.Mutex
	var validationWg sync.WaitGroup // Replaces pipelineWg
	var enrichWg sync.WaitGroup     // Dedicated to Phase 2

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	log.Println("[Engine] Spinning up background processing layers...")

	// 6. Spin up a pool of Validation Workers
	for i := 0; i < 5; i++ {
		validationWg.Add(1)
		go func() {
			defer validationWg.Done()
			for job := range validationChan {
				if vChain.Validate(job) {
					// log.Printf("[Validator] PASS: %s at %s\n", job.Title, job.Company)
					enrichmentChan <- job
				}
			}
		}()
	}

	// 7. Spin up a pool of Enrichment Workers
	for i := 0; i < 5; i++ {
		enrichWg.Add(1)
		go func() {
			defer enrichWg.Done()
			for job := range enrichmentChan {
				platform := job.Platform

				scr, exists := scrapersMap[platform]
				if !exists {
					log.Printf("[Enricher] No enrichment engine configured for platform: %v", platform)
					continue
				}

				enrichedJob, err := scr.Enrich(ctx, job)
				if err != nil {
					log.Printf("[Enricher] Error enriching job: %v", err)
					continue
				}

				resultsMu.Lock()
				finalResults = append(finalResults, enrichedJob)
				resultsMu.Unlock()
			}
		}()
	}

	log.Println("[Engine] Triggering concurrent scraping targets dynamically...")
	startTime := time.Now()

	// 8. Use a WaitGroup to manage our active, multi-threaded I/O Fetch routines
	var fetchWg sync.WaitGroup

	// 9. DYNAMIC DISPATCH LOOP: Replaces hardcoded blocks with the Python design pattern
	for platform, companies := range companiesDict {
		// Look up if a scraper driver is registered for this targeted key
		scr, exists := scrapersMap[platform]
		if !exists {
			log.Printf("[Engine] Skipping target loop: No scraper driver configured for platform %v\n", platform)
			continue
		}

		// Spin up a separate concurrent worker thread for every sub-company target
		for _, company := range companies {
			fetchWg.Add(1)

			// Pass the variables into the closure to prevent loop-variable race conditions
			go func(p models.JobPlatform, target string, s scraper.Scraper) {
				defer fetchWg.Done()
				// log.Printf("[Fetcher] Starting scrape for %s on %v\n", target, p)

				if err := s.Fetch(ctx, target, validationChan); err != nil {
					log.Printf("[Fetcher] Error running %v for %s: %v\n", p, target, err)
				}
			}(platform, company, scr)
		}
	}

	// 10. Wait for all dynamically spawned target routines to run to completion
	fetchWg.Wait()
	log.Println("[Engine] Raw network data collection completed. Closing fetch streams.")

	// Close the gate to the validation loop
	close(validationChan)

	// Wait ONLY for validators to finish processing their queue...
	validationWg.Wait()

	// ...now that validators are done, we know nothing else will be sent to the enrichment channel.
	// Close it safely.
	close(enrichmentChan)

	// Finally, wait for the enrichment workers to finish saving the last jobs to the results slice.
	enrichWg.Wait()

	validatorName := fmt.Sprintf("%T", vChain)
	vChain.PrintStats(validatorName)

	log.Printf("[Engine] Execution finished. Collected %d valid jobs in %v!\n", len(finalResults), time.Since(startTime))
}
