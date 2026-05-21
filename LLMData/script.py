import os
import json
import asyncio
import argparse
import uuid
import logging
from typing import Dict, Any, List

import openai
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_NAME = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
DEFAULT_OUTPUT_FILE = "acne_dataset.jsonl"
DEFAULT_SAMPLES = 20000
DEFAULT_BATCH_SIZE = 5

DISTRIBUTION = {
    "normalization": 0.20,
    "classification": 0.25,
    "recommendation": 0.35,
    "full_pipeline": 0.20
}

SYSTEM_PROMPT = "You are a senior dermatology AI dataset expert generating synthetic training data for a Vietnamese Acne Advisory system."

PROMPT_TEMPLATE = """Task Type: {task_type}

You must generate exactly {batch_size} unique, diverse, and high-quality data samples for this task.
Ensure medical consistency. Severity must ONLY be 'mild', 'moderate', or 'severe' following clinical guidelines.
Always append 'isotretinoin' or 'tetracycline' to the 'unsafe_flags' list if they are recommended or mentioned.
Use natural, diverse Vietnamese language for patient text. Use structured, clinical language for outputs.
Ensure random diversity in age, gender, symptoms, tone, and acne severity.

Output EXACTLY as a valid JSON object containing a list called "data".
Example: {{"data": [...]}}

Expected structure for each object in the list:
{expected_structure}

Random seed for diversity: {seed}
"""

STRUCTURES = {
    "normalization": """{
  "instruction": "Normalize the following patient statement.",
  "input": {
    "patient_statement": "<Vietnamese natural language, varied tones/dialects>",
    "demographics": {"age": <int>, "gender": "<Nam|Nu>"}
  },
  "output": {
    "normalized_description": "<clinical description>",
    "extracted_features": ["feature1", "feature2"],
    "ambiguities": ["ambiguity if any"]
  }
}""",
    "classification": """{
  "instruction": "Classify the acne based on the given features.",
  "input": {
    "structured_features": {"lesion_type": ["type1", "type2"], "locations": ["loc1"], "duration": "<string>"}
  },
  "output": {
    "acne_type": "<clinical acne type>",
    "severity": "<mild|moderate|severe>",
    "contributing_factors": ["factor1", "factor2"]
  }
}""",
    "recommendation": """{
  "instruction": "Provide acne treatment recommendations.",
  "input": {
    "classification_result": {"acne_type": "<type>", "severity": "<severity>"},
    "context": "<optional simulated RAG context, omit 40% of the time>"
  },
  "output": {
    "recommendations": {"first_line": ["rec1"], "second_line": ["rec2"]},
    "lifestyle_advice": ["advice1"],
    "monitoring": "<string>",
    "unsafe_flags": [],
    "uncertainty_statement": "<string>"
  }
}""",
    "full_pipeline": """{
  "instruction": "Process the patient text and provide comprehensive evaluation and recommendations.",
  "input": {
    "raw_patient_text": "<Vietnamese natural language>"
  },
  "output": {
    "structured_result": {
      "classification": {"acne_type": "<type>", "severity": "<mild|moderate|severe>"},
      "recommendations": {"first_line": ["rec1"], "second_line": ["rec2"]}
    },
    "reasoning": "<chain_of_thought string>",
    "unsafe_flags": [],
    "uncertainty_statement": "<string>"
  }
}"""
}

async def generate_batch(task_type: str, batch_size: int, client: AsyncOpenAI, semaphore: asyncio.Semaphore) -> List[Dict[str, Any]]:
    import random
    await asyncio.sleep(random.uniform(0.5, 2.0))
    async with semaphore:
        for attempt in range(10):
            try:
                expected_structure = STRUCTURES[task_type]
                user_prompt = PROMPT_TEMPLATE.format(
                    task_type=task_type,
                    batch_size=batch_size,
                    expected_structure=expected_structure,
                    seed=uuid.uuid4()
                )
                
                response = await client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.7,
                    response_format={"type": "json_object"}
                )
                
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("Empty response")
                
                raw_data = json.loads(content)
                data_list = raw_data.get("data", [])
                
                if not isinstance(data_list, list):
                    # Try to find any list in the object if "data" is missing
                    for v in raw_data.values():
                        if isinstance(v, list):
                            data_list = v
                            break
                    else:
                        raise ValueError("No list found in response")
                
                samples = []
                for data in data_list:
                    if "input" not in data or "output" not in data:
                        continue
                        
                    sample = {
                        "id": str(uuid.uuid4()),
                        "task_type": task_type,
                        "language": "vi",
                        "source": "synthetic",
                        "split": "train",
                        "instruction": data.get("instruction", ""),
                        "input": data.get("input", {}),
                        "output": data.get("output", {}),
                        "metadata": {},
                        "quality": {}
                    }
                    samples.append(sample)
                    
                if samples:
                    return samples
                
            except Exception as e:
                import random
                error_msg = str(e).lower()
                if "429" in error_msg or "rate limit" in error_msg or "too many" in error_msg:
                    sleep_time = 30 + (attempt * 20) + random.uniform(1, 10)
                    logger.warning(f"Rate limited (429). Sleeping for {sleep_time:.1f}s... (Attempt {attempt+1}/10)")
                    await asyncio.sleep(sleep_time)
                else:
                    logger.warning(f"API Error ({type(e).__name__}). Retrying in {2 ** attempt}s... (Attempt {attempt+1}/10)")
                    await asyncio.sleep(2 ** attempt)
                
        return []

async def worker(task_queue: asyncio.Queue, result_queue: asyncio.Queue, client: AsyncOpenAI, semaphore: asyncio.Semaphore):
    while True:
        try:
            task_type, batch_size = task_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
            
        samples = await generate_batch(task_type, batch_size, client, semaphore)
        if samples:
            await result_queue.put(samples)
            
        task_queue.task_done()

async def writer(result_queue: asyncio.Queue, output_file: str, total_samples: int, initial_count: int):
    count = initial_count
    
    with open(output_file, 'a', encoding='utf-8') as f:
        while True:
            samples = await result_queue.get()
            if samples is None:
                break
                
            for sample in samples:
                if count >= total_samples:
                    break
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
                count += 1
                
            f.flush()
            logger.info(f"Progress: {count}/{total_samples}")
            
            result_queue.task_done()
            if count >= total_samples:
                break

async def main():
    parser = argparse.ArgumentParser(description="Generate synthetic dataset for Acne Advisory LLM using DeepSeek")
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES, help="Total samples to generate")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Samples per API request")
    parser.add_argument("--output", type=str, default=DEFAULT_OUTPUT_FILE, help="Output JSONL file")
    parser.add_argument("--concurrency", type=int, default=3, help="Concurrent API requests")
    
    args = parser.parse_args()
    
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        logger.error("DEEPSEEK_API_KEY environment variable not set. Export it before running.")
        return
        
    client = AsyncOpenAI(api_key=api_key, base_url=BASE_URL)
    
    existing_samples = 0
    task_counts = {k: 0 for k in DISTRIBUTION}
    
    if os.path.exists(args.output):
        with open(args.output, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    t = data.get("task_type")
                    if t in task_counts:
                        task_counts[t] += 1
                    existing_samples += 1
                except ValueError:
                    pass
                    
    if existing_samples >= args.samples:
        logger.info(f"Dataset completely generated. Found {existing_samples} existing samples.")
        return
        
    logger.info(f"Resuming generation using DeepSeek. Existing: {existing_samples}. Target: {args.samples}")
    
    target_counts = {k: int(args.samples * v) for k, v in DISTRIBUTION.items()}
    target_counts["recommendation"] += args.samples - sum(target_counts.values())
    
    task_queue = asyncio.Queue()
    for t_type, t_target in target_counts.items():
        needed = max(0, t_target - task_counts[t_type])
        while needed > 0:
            b_size = min(args.batch_size, needed)
            task_queue.put_nowait((t_type, b_size))
            needed -= b_size
            
    if task_queue.empty():
        return
        
    logger.info(f"Queued {task_queue.qsize()} batches to hit targets.")
    
    result_queue = asyncio.Queue()
    semaphore = asyncio.Semaphore(args.concurrency)
    writer_task = asyncio.create_task(writer(result_queue, args.output, args.samples, existing_samples))
    
    workers = [asyncio.create_task(worker(task_queue, result_queue, client, semaphore)) for _ in range(min(args.concurrency, task_queue.qsize()))]
    
    await asyncio.gather(*workers)
    
    await result_queue.put(None)
    await writer_task
    
    logger.info(f"Generation successful. Output saved to {args.output}")

if __name__ == "__main__":
    asyncio.run(main())
