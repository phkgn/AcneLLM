"""Generate HTML report from visualizations."""
from __future__ import annotations
import json
from pathlib import Path
import base64
from datetime import datetime


def encode_image(img_path: Path) -> str:
    """Encode PNG as base64 for embedding in HTML."""
    with open(img_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_stats(docs: list[dict]) -> dict:
    """Quick stats."""
    if not docs:
        return {}
    text_lens = [len(d.get("text", "")) for d in docs if "text" in d]
    return {
        "count": len(docs),
        "avg_len": sum(text_lens) / len(text_lens) if text_lens else 0,
        "max_len": max(text_lens) if text_lens else 0,
        "min_len": min(text_lens) if text_lens else 0,
    }


def main():
    root = Path(__file__).parent
    docs_path = root.parent / "data" / "raw" / "documents.jsonl"
    llm_path = root.parent / "data" / "finetune" / "llm_data.jsonl"

    # Load data
    docs = []
    llm_data = []

    if docs_path.exists():
        with open(docs_path, "r", encoding="utf-8") as f:
            docs = [json.loads(line) for line in f if line.strip()]

    if llm_path.exists():
        with open(llm_path, "r", encoding="utf-8") as f:
            llm_data = [json.loads(line) for line in f if line.strip()]

    docs_stats = get_stats(docs)
    llm_stats = get_stats(llm_data)

    # Collect available images
    images = {}
    for img in sorted(root.glob("*.png")):
        try:
            images[img.stem] = encode_image(img)
        except Exception as e:
            print(f"⚠️  Failed to load {img.name}: {e}")

    # HTML
    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AcneLLM Dataset Visualization Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            padding: 40px;
        }}
        header {{
            text-align: center;
            border-bottom: 3px solid #3498DB;
            padding-bottom: 30px;
            margin-bottom: 40px;
        }}
        h1 {{
            font-size: 2.5em;
            color: #2C3E50;
            margin-bottom: 10px;
        }}
        .timestamp {{
            color: #7F8C8D;
            font-size: 0.9em;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
            padding: 30px;
            background: #F8F9FA;
            border-radius: 8px;
        }}
        .stat-card {{
            padding: 20px;
            background: white;
            border-radius: 6px;
            border-left: 4px solid #3498DB;
            box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        }}
        .stat-card.raw {{ border-left-color: #3498DB; }}
        .stat-card.llm {{ border-left-color: #E74C3C; }}
        .stat-label {{
            font-size: 0.85em;
            color: #7F8C8D;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .stat-value {{
            font-size: 1.8em;
            font-weight: bold;
            color: #2C3E50;
        }}
        .gallery {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(600px, 1fr));
            gap: 30px;
            margin: 40px 0;
        }}
        .chart-box {{
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            border: 1px solid #ECF0F1;
        }}
        .chart-title {{
            padding: 15px;
            background: #F8F9FA;
            border-bottom: 1px solid #ECF0F1;
            font-weight: 600;
            color: #2C3E50;
        }}
        .chart-img {{
            width: 100%;
            height: auto;
            display: block;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 30px 0;
            background: white;
            border-radius: 6px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        th, td {{
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #ECF0F1;
        }}
        th {{
            background: #34495E;
            color: white;
            font-weight: 600;
        }}
        tr:hover {{
            background: #F8F9FA;
        }}
        footer {{
            text-align: center;
            margin-top: 50px;
            padding-top: 30px;
            border-top: 1px solid #ECF0F1;
            color: #95A5A6;
            font-size: 0.9em;
        }}
        .section {{
            margin-bottom: 50px;
        }}
        .section-title {{
            font-size: 1.8em;
            color: #2C3E50;
            margin: 40px 0 20px 0;
            padding-bottom: 10px;
            border-bottom: 2px solid #3498DB;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 AcneLLM Dataset Visualization Report</h1>
            <p class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </header>

        <div class="section">
            <h2 class="section-title">Dataset Overview</h2>
            <div class="stats-grid">
                <div class="stat-card raw">
                    <div class="stat-label">📄 DocumentRaw Records</div>
                    <div class="stat-value">{docs_stats.get("count", 0):,}</div>
                </div>
                <div class="stat-card raw">
                    <div class="stat-label">📊 Avg. Text Length</div>
                    <div class="stat-value">{docs_stats.get("avg_len", 0) / 1000:.1f} KB</div>
                </div>
                <div class="stat-card llm">
                    <div class="stat-label">🎓 LLMData Records</div>
                    <div class="stat-value">{llm_stats.get("count", 0):,}</div>
                </div>
                <div class="stat-card llm">
                    <div class="stat-label">📊 Avg. Text Length</div>
                    <div class="stat-value">{llm_stats.get("avg_len", 0) / 1000:.1f} KB</div>
                </div>
            </div>

            <table>
                <thead>
                    <tr>
                        <th>Metric</th>
                        <th>DocumentRaw (RAG)</th>
                        <th>LLMData (Fine-tuning)</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>Total Records</strong></td>
                        <td>{docs_stats.get("count", 0):,}</td>
                        <td>{llm_stats.get("count", 0):,}</td>
                    </tr>
                    <tr>
                        <td><strong>Avg. Text Length</strong></td>
                        <td>{docs_stats.get("avg_len", 0) / 1000:.1f} KB</td>
                        <td>{llm_stats.get("avg_len", 0) / 1000:.1f} KB</td>
                    </tr>
                    <tr>
                        <td><strong>Max. Text Length</strong></td>
                        <td>{docs_stats.get("max_len", 0) / 1000:.1f} KB</td>
                        <td>{llm_stats.get("max_len", 0) / 1000:.1f} KB</td>
                    </tr>
                    <tr>
                        <td><strong>Min. Text Length</strong></td>
                        <td>{docs_stats.get("min_len", 0) / 1000:.1f} KB</td>
                        <td>{llm_stats.get("min_len", 0) / 1000:.1f} KB</td>
                    </tr>
                    <tr>
                        <td><strong>Primary Format</strong></td>
                        <td>Full metadata + HTML metrics</td>
                        <td>Alpaca-style instruction-tuning</td>
                    </tr>
                    <tr>
                        <td><strong>Use Case</strong></td>
                        <td>RAG retrieval & chunking</td>
                        <td>LLM fine-tuning augmentation</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="section">
            <h2 class="section-title">Visualizations</h2>
            <div class="gallery">
"""

    # Add charts
    chart_titles = {
        "01_language_distribution": "Language Distribution (VI vs EN)",
        "02_trust_level": "Trust Level Breakdown",
        "03_top_sources": "Top Data Sources",
        "04_text_length": "Text Length Distribution",
        "05_quality_scores": "Document Quality Scores",
        "06_categories": "Content Category Distribution",
    }

    for chart_id, title in chart_titles.items():
        if chart_id in images:
            html += f"""                <div class="chart-box">
                    <div class="chart-title">{title}</div>
                    <img src="data:image/png;base64,{images[chart_id]}" alt="{title}" class="chart-img">
                </div>
"""

    html += """            </div>
        </div>

        <div class="section">
            <h2 class="section-title">Format Comparison</h2>
            <table>
                <thead>
                    <tr>
                        <th>Aspect</th>
                        <th>DocumentRaw</th>
                        <th>LLMData</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>Purpose</strong></td>
                        <td>RAG knowledge base</td>
                        <td>Fine-tuning dataset</td>
                    </tr>
                    <tr>
                        <td><strong>Key Fields</strong></td>
                        <td>url, title, text, quality_score, source, categories, tags</td>
                        <td>instruction, input, output, metadata</td>
                    </tr>
                    <tr>
                        <td><strong>Text Field</strong></td>
                        <td><code>text</code> (cleaned HTML extraction)</td>
                        <td><code>output</code> (same content as text)</td>
                    </tr>
                    <tr>
                        <td><strong>Instruction</strong></td>
                        <td>N/A</td>
                        <td>Auto-generated from title (VI/EN template)</td>
                    </tr>
                    <tr>
                        <td><strong>Quality Metadata</strong></td>
                        <td>quality_score (0.0-1.0)</td>
                        <td>In metadata (source trust_level)</td>
                    </tr>
                    <tr>
                        <td><strong>Use Case</strong></td>
                        <td>Semantic search, context retrieval for RAG</td>
                        <td>Instruction-following model training</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <footer>
            <p>Generated by AcneLLM Visualization Pipeline</p>
            <p>DocumentRaw: RAG Knowledge Base | LLMData: Fine-tuning Augmentation Dataset</p>
        </footer>
    </div>
</body>
</html>
"""

    output_path = root / "report.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ HTML report saved to {output_path}")
    print(f"   Open in browser: file://{output_path.absolute()}")


if __name__ == "__main__":
    main()
