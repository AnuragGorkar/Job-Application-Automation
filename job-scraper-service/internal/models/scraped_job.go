package models

import "time"

type ScrapedJob struct {
	URL         string      `json:"url"`
	Company     string      `json:"company"`
	Title       string      `json:"title"`
	Description string      `json:"description"`
	Location    string      `json:"location"`
	PostedAt    *time.Time  `json:"posted_at"`
	Platform    JobPlatform `json:"platform"`
}
