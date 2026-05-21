#!/bin/bash
# Run dataset visualization and analysis

set -e

echo "📊 AcneLLM Dataset Visualization"
echo "================================="
echo ""

# Check if data exists
DOCS_FILE="../data/processed/documents.jsonl"
LLM_FILE="../data/processed/llm_data.jsonl"

if [ ! -f "$DOCS_FILE" ]; then
    echo "⚠️  $DOCS_FILE not found"
    echo "   Run: python -m scripts.crawl_all"
    exit 1
fi

echo "✓ Found data files:"
echo "  - $DOCS_FILE"
[ -f "$LLM_FILE" ] && echo "  - $LLM_FILE" || echo "  ⚠️  $LLM_FILE (will be created by crawl_all.py)"
echo ""

echo "📈 Generating visualizations..."
python plot_datasets.py

echo ""
echo "✅ Done! Open PNG files or README.md to view results"
