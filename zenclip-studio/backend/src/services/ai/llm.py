from services.ai.llm_provider import generate_llm_response
import re
import os

def auto_fix_transcript_with_llm(phrase_timings, api_key, api_provider='deepseek'):
    """
    Use LLM to automatically fix typos in transcript using robust JSON processing.
    """
    if not api_key:
        raise ValueError("API key is required")
    
    # Optimize: Only send text and IDs to save tokens
    mini_transcript = [
        {"id": i, "text": p['text']} 
        for i, p in enumerate(phrase_timings)
    ]
    
    # Chunking strategy
    CHUNK_SIZE = 50
    chunks = [mini_transcript[i:i + CHUNK_SIZE] for i in range(0, len(mini_transcript), CHUNK_SIZE)]
    print(f"[INFO] Split transcript into {len(chunks)} chunks for parallel fixing...")

    import json
    import concurrent.futures

    def process_chunk(chunk_index, chunk_data):
        chunk_json = json.dumps(chunk_data, ensure_ascii=False)
        prompt = f"""
You are a professional transcript editor. 
Your task is to fix typos, spelling mistakes, and grammar errors in the following JSON transcript chunk.

RULES:
1. Fix ONLY errors (spelling, capitalization, punctuation).
2. DO NOT change the meaning.
3. Return a JSON OBJECT where keys are the "id" and values are the "corrected text".
4. ***IMPORTANT: INCLUDE ONLY THE ITEMS THAT YOU CHANGED. DO NOT RETURN UNCHANGED ITEMS.***
5. Output format example: {{ "2": "Fixed text here", "5": "Another fix" }}

INPUT DATA:
{chunk_json}
"""
        try:
            response_text = generate_llm_response(
                prompt=prompt,
                system_instruction="Return only valid JSON object of corrections. No markdown.",
                api_key=api_key,
                provider=api_provider
            )
            
            # Clean response
            response_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
            if not response_text or response_text == '{}':
                return {}
                
            return json.loads(response_text)
        except Exception as e:
            print(f"[WARN] Chunk {chunk_index} failed: {e}")
            return {}

    # Parallel Execution
    all_corrections = {}
    
    # Max workers limit to avoid rate limits (DeepSeek/Gemini can be strict)
    # 5 workers * 50 phrases = 250 phrases processed at once.
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_chunk = {
            executor.submit(process_chunk, i, chunk): i 
            for i, chunk in enumerate(chunks)
        }
        
        for future in concurrent.futures.as_completed(future_to_chunk):
            i = future_to_chunk[future]
            try:
                chunk_corrections = future.result()
                if chunk_corrections:
                    all_corrections.update(chunk_corrections)
                    print(f"[SUCCESS] Chunk {i} processed: {len(chunk_corrections)} corrections")
                else:
                    print(f"[SUCCESS] Chunk {i} processed: No corrections")
            except Exception as e:
                print(f"[ERROR] Chunk {i} exception: {e}")

    # Apply corrections
    fixed_phrase_timings = []
    fix_count = 0
    
    for i, phrase in enumerate(phrase_timings):
        str_id = str(i)
        new_text = all_corrections.get(str_id)
        
        if new_text and new_text != phrase['text']:
            fixed_phrase_timings.append({**phrase, 'text': new_text})
            fix_count += 1
        else:
            fixed_phrase_timings.append(phrase)
            
    print(f"[SUCCESS] Auto-fix complete: {fix_count} phrases corrected")
    return fixed_phrase_timings
