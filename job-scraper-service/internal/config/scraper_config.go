package config

import "time"

type ScraperConfig struct {
	MaxConnections        int
	MaxKeepAlive          int
	MaxRetries            int
	BaseDelay             time.Duration
	GlobalSemaphoreValue  int
	BaseATSFetchSemaphore int
}

func DefaultConfig() *ScraperConfig {
	return &ScraperConfig{
		MaxConnections:        100,
		MaxKeepAlive:          20,
		MaxRetries:            3,
		BaseDelay:             2 * time.Second,
		GlobalSemaphoreValue:  5,
		BaseATSFetchSemaphore: 20,
	}
}
