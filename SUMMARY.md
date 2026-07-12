# Daily Brief - Project Summary

## v0.2.5-BETA12

### 📝 Overview 
Automated news aggregation and summarization system with improved configuration, cleanup, and output formatting.

### 📈 Change Log
- [2026-07-12 20:24] Feature - Added configuration system via config.py
- [2026-07-12 20:24] Feature - Enhanced date/time display to show full datetime instead of just date
- [2026-07-12 20:24] Feature - Cleaned up output formatting (removed H3 headers)
- [2026-07-12 20:24] Feature - Implemented proper cleanup logic to maintain MAX_VERSIONS most recent files in both logs and news directories  
- [2026-07-12 20:24] Feature - Removed alert system from output
- [2026-07-12 20:24] Feature - Improved article content extraction from external URLs
- [2026-07-12 20:24] Feature - Increased context window size to 8192 and later 16384
- [2026-07-12 20:24] Feature - Enhanced weather fetching with proper timeout handling
- [2026-07-12 20:24] Fix - Resolved alerts_list variable reference error 