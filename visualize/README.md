# Dataset Visualization Summary

## DocumentRaw (RAG Knowledge Base)
- **Total Documents**: 0
- **Languages**: {}
- **Trust Levels**: {}
- **Avg Text Length**: 0.0 KB
- **Avg Quality Score**: 0.500
- **Top 5 Sources**:


## LLMData (Fine-tuning Dataset)
- **Total Records**: 0
- **Languages**: {}
- **Trust Levels**: {}
- **Avg Text Length**: 0.0 KB
- **Top 5 Sources**:


## Data Format Differences
| Aspect | DocumentRaw | LLMData |
|--------|-------------|---------|
| **Purpose** | RAG retrieval & chunking | Fine-tuning LLM |
| **Fields** | url, title, text, html_len, quality_score, source, categories, tags | instruction, input, output, metadata |
| **Key Field** | `text` (extracted HTML content) | `output` (same as text) |
| **Instruction** | None | Generated from title (VI/EN templates) |
| **Use Case** | Semantic search, RAG context | LLM instruction-following training |
