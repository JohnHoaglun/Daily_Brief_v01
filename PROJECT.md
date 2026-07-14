# Project: Daily Brief v01

## 📝 Overview
Automated daily news brief generator that fetches news from 17 content categories and produces Markdown reports with AI summaries using Ollama.

## 🏗️ Architecture
- **RSS Feed Integration**: Pulls news from multiple sources using feedparser
- **Content Processing**: Batch summarization via Ollama (one call per category) 
- **Data Organization**: Stories grouped by 17 categories including World News, US News, Texas News, etc.
- **Tagging System**: Automatic keyword-based tagging of stories using predefined mappings

## 🔧 Configuration
The project uses a configuration file (`config.txt`) that defines all settings:
- LLM_MODEL: Model for summarization (default: mistral)  
- LOG_DIR: Directory for log files
- NEWS_DIR: Directory for news data storage
- CATEGORIES: 17 content categories with story limits

## 🚀 Features
- Automated daily news aggregation 
- AI-powered story summarization via batch processing
- Multi-category organization by source feeds
- Configurable story limits per category
- Performance optimized with batched LLM calls
- Weather data integration 
- Automatic keyword-based tagging of stories

## 📈 Status
Fully functional and working correctly. The pipeline successfully fetches weather data, pulls news from RSS feeds, processes stories with LLM summarization via batch processing, and generates output reports.