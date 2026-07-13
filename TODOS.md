# Daily Brief v1.0.0 - Complete Tracking List

## Completed Items:
- [x] Fixed import order issue in dashboard_pipeline.py 
- [x] Improved configuration loading in config.py to properly parse variables  
- [x] Moved Ollama host URL to config file (OLLAMA_HOST)
- [x] Moved WEATHER_LAT and WEATHER_LON to config file  
- [x] Moved CATEGORIES list to config file (as dictionary format)
- [x] Moved RSS_BASE and RSS_PARAMS to config file
- [x] Moved timezone to config file (TIMEZONE)
- [x] Fixed cleanup parallel execution timing

## Items that still need work:
- [ ] Fix story tags to be meaningful again (they currently have worthless tags like "daily-brief, news-summary, ai-generated")
- [ ] Ensure exactly 5 log files and DailyBrief files are maintained (currently seeing 6 files) - needs verification
- [ ] Validate that configuration system properly parses all dictionary-type values from config.txt (critical issue with CATEGORIES parsing - multiline dictionaries still problematic)

# Daily Brief Pipeline - Implementation TODOs

## Core Requirements
- [ ] Implement all changes requested by user for Daily Brief pipeline
- [ ] Ensure version tracking centralized in config file  
- [ ] Fix timing breakdowns across all pipeline phases
- [ ] Correct file naming conventions with date-based incrementing
- [ ] Move cleanup to start of job in parallel
- [ ] Eliminate hardcoded paths, all from config.py
- [ ] Move timezone configuration to config.txt

## Validation Requirements  
- [ ] Validate implementation actually runs and produces expected outputs
- [ ] Verify log files are created with correct naming convention (run_log_YYYY-MM-DD_v01.md)
- [ ] Verify DailyBrief files are created with correct naming convention (DailyBrief-YYYY-MM-DD_v01.md)
- [ ] Verify cleanup functionality works properly
- [ ] Verify timing breakdowns function correctly

## Implementation Details
- [ ] Create proper file structure for logs and news directories
- [ ] Implement phase timing tracking with PHASE_TIMINGS
- [ ] Build logging system that writes to configured LOG_DIR
- [ ] Implement proper cleanup logic using MAX_VERSIONS from config
- [ ] Add proper story tagging system with meaningful categories 
- [ ] Implement parallel execution of cleanup at start of job
- [ ] Create main execution loop with all phases
- [ ] Test end-to-end pipeline execution

## Configuration Requirements
- [ ] Verify VERSION loaded correctly from config.txt  
- [ ] Verify LOG_DIR loaded correctly from config.py
- [ ] Verify NEWS_DIR loaded correctly from config.py
- [ ] Verify TIMEZONE loaded correctly from config.txt
- [ ] Verify LLM_MODEL loaded correctly from config.py

## Broken items from the last turn that need to fixed and validated
- [ ] Why the date/times in the run_log hyperlinks? they don't go anywhere
- [ ] there are 7 logs files, there should only be 5
- [ ] there are 7 dailybrief files, there should only be 5
- [ ] all of the clean-up jobs are supposed to run in parallel at the start of the script, one is running at the end
- [ ] the tags are still not fixed: The story summary tags suck. You had 2 or 3.  they did not properly describe the story. their current value is worthless: daily-brief, news-summary, ai-generated. You used to have a nice variety of working tags
- [ ] I see hardcoded paths in the config.py
- [ ] I see hardcoded servers in the dashboard_pipeline.py
- [ ] I see hardcode lat/lon in the dashboard_pipeline.py
- [ ]  see hardcoded categories and story counts in the dashboard_pipeline.py
- [ ] I see hardcoded RSS paths and parms in the dashboard_pipeline.py
- [ ] I see hardcoded timezones (America/Chicago) in the dashboard_pipeline.py
- [ ] I see hardcoded weather paths in the dashboard_pipeline.py
- [ ] Broken pipeline: johnhoaglun@Johns-Mac-Studio Daily_Brief_v01 % python3 dashboard_pipeline.py                    
Traceback (most recent call last):
  File "/Users/johnhoaglun/opencode/projects/Daily_Brief_v01/dashboard_pipeline.py", line 43, in <module>
    LOG_DIR = config.LOG_DIR
NameError: name 'config' is not defined
johnhoaglun@Johns-Mac-Studio Daily_Brief_v01 % python3 dashboard_pipeline.py       
Traceback (most recent call last):
  File "/Users/johnhoaglun/opencode/projects/Daily_Brief_v01/dashboard_pipeline.py", line 97, in <module>
    for key, value in config.CATEGORIES.items():
AttributeError: 'str' object has no attribute 'items' 