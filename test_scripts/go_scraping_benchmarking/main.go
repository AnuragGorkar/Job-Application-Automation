package main

import (
	"crypto/tls"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"sync"
	"time"
)

// Simulates the exact same heavy CPU text processing
func heavyCpuProcessing(text string) int {
	cleaned := text
	reg := regexp.MustCompile(`[^a-zA-Z0-9\s]`)
	for i := 0; i < 50000; i++ {
		cleaned = reg.ReplaceAllString(cleaned, "")
	}
	return len(cleaned)
}

func fetchAndProcess(client *http.Client, url string, wg *sync.WaitGroup) {
	defer wg.Done()

	// 1. Network I/O
	resp, err := client.Get(url)
	if err != nil {
		return
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return
	}

	// 2. Heavy CPU Block (Go runs this on a separate OS thread automatically)
	_ = heavyCpuProcessing(string(body))
}

func main() {
	url := "https://httpbin.org/bytes/1024"

	// Configure connection pooling similar to httpx
	tr := &http.Transport{
		MaxIdleConns:        100,
		MaxIdleConnsPerHost: 20,
		TLSClientConfig:     &tls.Config{InsecureSkipVerify: true},
	}
	client := &http.Client{
		Transport: tr,
		Timeout:   10 * time.Second,
	}

	var wg sync.WaitGroup
	startTime := time.Now()

	// Dispatch 100 concurrent goroutines
	for i := 0; i < 10000; i++ {
		wg.Add(1)
		go fetchAndProcess(client, url, &wg)
	}

	wg.Wait()
	fmt.Printf("Go Total Time: %v\n", time.Since(startTime))
}