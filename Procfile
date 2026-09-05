web: bash -c "cd pipeline && python -m ingest.build_catalog && cd ../backend && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
