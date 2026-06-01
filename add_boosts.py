#!/usr/bin/env python3
"""Add source boost configs to settings.py"""
import re

content = open('src/acne_llm/config.py', encoding='utf-8').read()

boost_config = '''
    # ── Retrieval source boost (tune riêng) ───────────────────────────
    # Dùng trong rag/retriever.py thay vì hardcode
    retrieval_source_boosts: dict = {
        "nice_guideline": 1.50,
        "aad_guideline": 1.50,
        "jid_paper": 1.30,
        "pubmed_review": 1.20,
        "clinical_textbook": 1.20,
        "vi_medical_site": 1.00,
        "forum_post": 0.80,
        "blog": 0.70,
        "unknown": 1.00,
    }
    retrieval_trust_boosts: dict = {"high": 1.40, "medium": 1.00, "low": 0.70}
    retrieval_authority_boost: float = 1.15
'''

# Find insertion point - after chat_rerank_top_k_clinical
pattern = r'(chat_rerank_top_k_clinical: int = \d+)'
match = re.search(pattern, content)
if match:
    pos = match.end()
    content = content[:pos] + boost_config + '\n' + content[pos:]
    open('src/acne_llm/config.py', 'w', encoding='utf-8', newline='\n').write(content)
    print('Added boost configs!')
else:
    print('Pattern not found')
