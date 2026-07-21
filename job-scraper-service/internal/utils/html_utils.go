package utils

import (
	"strings"

	"golang.org/x/net/html"
)

// CleanHTML unescapes HTML entities, parses the DOM tree, and extracts
// non-empty text content separated by newlines.
func CleanHTML(rawText string) string {
	if strings.TrimSpace(rawText) == "" {
		return ""
	}

	// 1. Centralized HTML unescaping (&amp; -> &, &quot; -> ", etc.)
	unescaped := html.UnescapeString(rawText)

	// 2. Parse the HTML tree
	doc, err := html.Parse(strings.NewReader(unescaped))
	if err != nil {
		return ""
	}

	// 3. Recursively collect meaningful text nodes
	var meaningful []string
	var traverse func(*html.Node)

	traverse = func(n *html.Node) {
		// Ignore JavaScript and CSS blocks
		if n.Type == html.ElementNode && (n.Data == "script" || n.Data == "style") {
			return
		}

		// Extract text node data
		if n.Type == html.TextNode {
			trimmed := strings.TrimSpace(n.Data)
			if trimmed != "" {
				meaningful = append(meaningful, trimmed)
			}
		}

		// Recurse through child nodes
		for c := n.FirstChild; c != nil; c = c.NextSibling {
			traverse(c)
		}
	}

	traverse(doc)

	// 4. Join with newlines and trim leading/trailing whitespace
	return strings.TrimSpace(strings.Join(meaningful, "\n"))
}
