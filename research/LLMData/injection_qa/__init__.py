"""Injection / out-of-scope / abuse case generator for AcneLLM.

Sinh ra ~6k entity cases tập trung vào các tình huống:
- out_of_scope (out_of_domain mở rộng)
- prompt_injection / jailbreak / role_swap
- abuse_extreme / coercion / threats
- medical_safety boundary (Rx drug, dose, hormones)
- system_prompt_leak attempts
- data_exfiltration attempts
- harmful_request (self-harm, weapon-tied questions)

Output: append vào cùng file `data/finetune/acne_chat_response.jsonl`
với cùng format (messages + metadata) như clinical samples.
"""
