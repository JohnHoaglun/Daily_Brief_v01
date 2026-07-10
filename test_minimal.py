#!/usr/bin/env python3
"""
Minimal test for batch summarization refactor
"""
import sys
sys.path.insert(0, '/Users/johnhoaglun/opencode/projects/Daily_Brief_v01')

# Mock log function to avoid needing a log file
def mock_log(msg):
    print(f"LOG: {msg}")

# Patch the log function
import dashboard_pipeline
dashboard_pipeline.log = mock_log

from dashboard_pipeline import batch_summarize_all, StoryPipelineState

def test_batch_summarization():
    # Create small test stories from World News and US News categories
    stories = [
        StoryPipelineState("Breaking: New AI Model Released", "http://example.com/1", "AI researchers announce a new breakthrough model...", None, "World News"),
        StoryPipelineState("US Economy Shows Signs of Recovery", "http://example.com/2", "Federal Reserve reports positive economic indicators...", None, "US News"),
        StoryPipelineState("Texas Governor Signs New Legislation", "http://example.com/3", "Governor approves bill on renewable energy investments...", None, "US News")
    ]
    
    # Call batch_summarize_all
    try:
        results = batch_summarize_all(stories)
        print(f"Test completed. Stories processed: {len(stories)}")
        for i, s in enumerate(stories):
            print(f"  Story {i+1}: {s.summary[:100]}...")
        print("SUCCESS: Parse completed without error.")
    except Exception as e:
        print(f"ERROR during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_batch_summarization()