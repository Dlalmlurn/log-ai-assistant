#!/usr/bin/env bash
set -euo pipefail

# 1) Init Kafka topics + Elasticsearch indices
python src/main.py init

# 2) Generate demo logs with mentor log-generator
python src/main.py inspect-generator
python src/main.py produce --run-generator --days 1 --count 120

# 3) Fallback processor (use this when Flink job is not running)
python src/main.py process-raw --max-messages 10000

# 4) Start consumer to write parsed_logs/alert_events into Elasticsearch
python src/main.py consume-to-es --max-messages 10000

# 5) Build baseline + analyze alerts + daily report
python src/main.py build-baseline
python src/main.py analyze-alerts --limit 50
python src/main.py report

echo "Pipeline run complete. Start dashboard with: streamlit run src/dashboard/app.py"
