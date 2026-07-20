package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"time"
)

type ScrapedJob struct {
	Title       string `json:"title"`
	Location    string `json:"location"`
	Description string `json:"description"`
	PostedAt    string `json:"posted_at"`
	URL         string `json:"url"`
	Company     string `json:"company"`
	Platform    string `json:"platform"`
}

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

// mapToScrapedJob converts the raw Greenhouse API model to our universal application model.
func mapToScrapedJob(ghJob GreenhouseJob, companyName string) ScrapedJob {
	return ScrapedJob{
		Title:       ghJob.Title,
		Location:    ghJob.Location.Name,
		Description: ghJob.Content, // We will handle HTML stripping in a later lesson
		PostedAt:    ghJob.UpdatedAt,
		URL:         ghJob.AbsoluteURL,
		Company:     companyName,
		Platform:    "greenhouse",
	}
}

func main() {
	companyName := "cloudflare"
	// Replicating your Python URL: https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true
	url := fmt.Sprintf("https://boards-api.greenhouse.io/v1/boards/%s/jobs?content=true", companyName)

	// 1. Initialize a reusable http.Client with a timeout (Crucial for production!)
	client := &http.Client{
		Timeout: 10 * time.Second,
	}

	log.Printf("Fetching jobs for %s...", companyName)

	// 2. Perform the GET request
	resp, err := client.Get(url)
	if err != nil {
		log.Fatalf("Network request failed: %v", err)
	}

	// 3. CRITICAL GO PATTERN: Always close the response body to prevent resource leaks.
	// `defer` guarantees this runs when main() completes.
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		log.Fatalf("API returned non-200 status: %d", resp.StatusCode)
	}

	// 4. Read the raw stream of bytes from the response body
	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		log.Fatalf("Failed to read response body: %v", err)
	}

	// 5. Parse (Unmarshal) the JSON bytes directly into our GreenhouseResponse struct
	var ghResponse GreenhouseResponse
	err = json.Unmarshal(bodyBytes, &ghResponse)
	if err != nil {
		log.Fatalf("Failed to parse JSON: %v", err)
	}

	log.Printf("Successfully parsed %d jobs from Greenhouse!", len(ghResponse.Jobs))

	// 6. Map and print out the first 3 jobs to verify
	for i, ghJob := range ghResponse.Jobs {
		if i >= 3 {
			break
		}
		scrapedJob := mapToScrapedJob(ghJob, companyName)
		fmt.Printf("[%d] Title: %s | Location: %s\n", i+1, scrapedJob.Title, scrapedJob.Location)
	}
}
