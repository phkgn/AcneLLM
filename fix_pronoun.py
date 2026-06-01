#!/usr/bin/env python3
import re

with open('src/acne_llm/chat/intent_router.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = r't[ớo]|tao|chau|to)'
new = r'tôi|toi|t[ớo]|tao|mình|minh)'

if old in content:
    content = content.replace(old, new)
    with open('src/acne_llm/chat/intent_router.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed pronoun regex!')
else:
    print('Pattern not found')
