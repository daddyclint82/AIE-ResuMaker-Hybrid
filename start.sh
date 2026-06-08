#!/bin/bash
# AIe ResuMaker — Startup script
# Usage: ./start.sh [dev|prod]

ENV="${1:-dev}"

if [ "$ENV" == "prod" ] || [ "$ENV" == "production" ]; then
    echo "Starting AIe ResuMaker in PRODUCTION mode..."
    export APP_ENV=production
else
    echo "Starting AIe ResuMaker in DEVELOPMENT mode..."
    export APP_ENV=development
fi

# Activate virtual environment
source venv/bin/activate

# Start server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
