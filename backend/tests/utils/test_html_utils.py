import pytest
from app.utils.html_utils import clean_html

# ==============================================================================
# 1. Edge Cases & Null Inputs
# ==============================================================================

@pytest.mark.parametrize("raw_input, expected", [
    ("", ""),
    (None, ""),
    ("   ", ""),
])
def test_clean_html_empty_and_null_inputs(raw_input, expected):
    """Ensures the function safely handles missing, null, or whitespace-only inputs without crashing."""
    assert clean_html(raw_input) == expected


# ==============================================================================
# 2. HTML Entity Unescaping
# ==============================================================================

@pytest.mark.parametrize("raw_input, expected", [
    ("Software &amp; Engineering", "Software & Engineering"),
    ("Experience with &quot;Python&quot; &amp; &#39;Go&#39;", 'Experience with "Python" & \'Go\''),
    ("Salary &lt; $100k &gt; $50k", "Salary < $100k > $50k"),
    ("Remote&nbsp;Work", "Remote\xa0Work"), # \xa0 is the unicode non-breaking space
    ("&#128640; Fast growing startup!", "🚀 Fast growing startup!"),
])
def test_clean_html_unescapes_entities(raw_input, expected):
    """Verifies that standard, numeric, and hex HTML entities are converted to actual characters."""
    assert clean_html(raw_input) == expected


# ==============================================================================
# 3. Block Level Tags & Layout formatting
# ==============================================================================

@pytest.mark.parametrize("raw_input, expected", [
    # Basic paragraph block
    ("<p>Welcome to our company.</p>", "Welcome to our company."),
    
    # Multiple paragraphs should be separated by the defined newline separator
    ("<p>Paragraph 1</p><p>Paragraph 2</p>", "Paragraph 1\nParagraph 2"),
    
    # Divs and line breaks
    ("<div>Line 1<br>Line 2<br/>Line 3</div>", "Line 1\nLine 2\nLine 3"),
    
    # Header tags
    ("<h1>Job Title</h1><h2>Responsibilities</h2>", "Job Title\nResponsibilities"),
])
def test_clean_html_block_tags(raw_input, expected):
    """Ensures block-level elements are stripped and properly separated by newlines."""
    assert clean_html(raw_input) == expected


# ==============================================================================
# 4. Inline Tags (Documenting the Newline Quirk)
# ==============================================================================

@pytest.mark.parametrize("raw_input, expected", [
    # Because get_text(separator="\n") is used, EVERY tag boundary inserts a newline.
    # This documents the exact behavior that caused the Workday test failure earlier.
    ("<p>This is <strong>bold</strong> text.</p>", "This is \nbold\n text."),
    ("Looking for an <em>expert</em> engineer.", "Looking for an \nexpert\n engineer."),
    ("Click <a href='https://example.com'>here</a> to apply.", "Click \nhere\n to apply."),
    ("Build <span>scalable</span> APIs", "Build \nscalable\n APIs"),
])
def test_clean_html_inline_tag_newline_behavior(raw_input, expected):
    """
    Documents how BeautifulSoup's separator argument interacts with inline tags.
    Note: If this behavior is undesirable for ATS job descriptions, the `clean_html` 
    function will need to be refactored to replace block tags manually before calling get_text.
    """
    assert clean_html(raw_input) == expected


# ==============================================================================
# 5. Lists and Bullet Points (Crucial for Resumes/Jobs)
# ==============================================================================

@pytest.mark.parametrize("raw_input, expected", [
    # Standard Unordered List
    ("<ul><li>Python</li><li>AWS</li><li>Go</li></ul>", "Python\nAWS\nGo"),
    
    # Standard Ordered List
    ("<ol><li>Step 1</li><li>Step 2</li></ol>", "Step 1\nStep 2"),
    
    # Messy list with extra whitespace inside the HTML payload
    (
        "<ul>\n  <li>Distributed Systems</li>\n  <li>Microservices</li>\n</ul>", 
        "Distributed Systems\nMicroservices"
    ),
])
def test_clean_html_extracts_lists(raw_input, expected):
    """Verifies that job requirement lists are cleanly extracted into newline-separated text."""
    assert clean_html(raw_input) == expected


# ==============================================================================
# 6. Malformed & Messy HTML
# ==============================================================================

@pytest.mark.parametrize("raw_input, expected", [
    # Missing closing tags
    ("<div><p>Unclosed paragraph", "Unclosed paragraph"),
    
    # Stray closing tags
    ("No opening tag</div></p>", "No opening tag"),
    
    # Mixed nesting chaos
    ("<b><i>Messy <span>Nesting</b></i></span>", "Messy \nNesting"),
])
def test_clean_html_handles_malformed_input(raw_input, expected):
    """Ensures BeautifulSoup gracefully parses broken HTML common in old ATS systems."""
    assert clean_html(raw_input) == expected


# ==============================================================================
# 7. Comprehensive Real-World Payload Test
# ==============================================================================

def test_clean_html_full_job_description():
    """Simulates a complete, messy JSON payload response from a generic ATS."""
    real_world_payload = (
        "&lt;h1&gt;Senior Software Engineer&lt;/h1&gt;"
        "&lt;p&gt;Join our &amp;quot;amazing&amp;quot; team!&lt;/p&gt;"
        "&lt;h3&gt;Requirements:&lt;/h3&gt;"
        "&lt;ul&gt;"
        "&lt;li&gt;5+ years of &lt;strong&gt;Python&lt;/strong&gt;&lt;/li&gt;"
        "&lt;li&gt;Experience with AWS, GCP, or Azure&lt;/li&gt;"
        "&lt;/ul&gt;"
        "&lt;br&gt;&lt;p&gt;Remote&amp;nbsp;Friendly&lt;/p&gt;"
    )
    
    # Because of the inline tag separator behavior tested in section 4, 
    # the <strong> tag around Python will create wrapping newlines.
    expected_output = (
        "Senior Software Engineer\n"
        'Join our "amazing" team!\n'
        "Requirements:\n"
        "5+ years of \nPython\n"
        "Experience with AWS, GCP, or Azure\n"
        "Remote\xa0Friendly"
    )
    
    assert clean_html(real_world_payload) == expected_output