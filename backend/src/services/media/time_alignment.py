import re

def _get_closure_score(text):
    """
    Score how well a phrase provides closure/completion.
    Higher score = better ending point
    
    IMPROVED: Also checks for complete sentences WITHIN the phrase
    """
    text = text.strip()
    if not text:
        return 0
    
    score = 0
    
    # Check if phrase ends with strong closure
    if text.endswith('.') or text.endswith('。'):
        score += 10
    elif text.endswith('!') or text.endswith('！'):
        score += 10
    elif text.endswith('?') or text.endswith('？'):
        score += 9
    elif text.endswith(':') or text.endswith('：'):
        score += 5
    elif text.endswith(',') or text.endswith('，'):
        score += 2
    else:
        # Phrase doesn't end with punctuation - CHECK INTERNAL SENTENCES
        # Look for last complete sentence within the phrase
        # Find all sentence-ending punctuation positions
        sentence_ends = list(re.finditer(r'[.!?。！？]', text))
        
        if sentence_ends:
            # There's a complete sentence inside, but phrase continues after
            last_end = sentence_ends[-1]
            remaining_text = text[last_end.end():].strip()
            
            if remaining_text:
                # There's incomplete text after the last sentence
                # Penalize heavily - this phrase ends mid-sentence
                score -= 8
                
                # Check what the incomplete part starts with
                incomplete_starters = [
                    'jadi', 'terus', 'nah', 'dan', 'tapi', 'karena', 'yang',
                    'so', 'then', 'and', 'but', 'because', 'which', 'that'
                ]
                first_word = remaining_text.lower().split()[0] if remaining_text.split() else ''
                if first_word.rstrip(',') in incomplete_starters:
                    score -= 5  # Even worse - starts new thought but doesn't finish
    
    # Indonesian/English conclusive phrases (at very end of text)
    conclusive_words = [
        # Indonesian
        'gitu', 'itu', 'kan', 'ya', 'dong', 'sih', 'loh', 'nih',
        'jadi', 'makanya', 'intinya', 'pokoknya', 'akhirnya', 'kesimpulannya',
        # English  
        'right', 'okay', 'so', 'yeah', 'done', 'yes', 'finally', 'basically',
        'exactly', 'absolutely', 'indeed', 'actually'
    ]
    
    words = text.lower().split()
    if words:
        last_word = words[-1].rstrip('.,!?')
        if last_word in conclusive_words:
            score += 3
        
        # Penalize ending on conjunctions/incomplete indicators
        incomplete_indicators = [
            'dan', 'tapi', 'atau', 'karena', 'kalau', 'jika', 'yang', 'dengan', 
            'untuk', 'di', 'ke', 'dari', 'mereka', 'itu', 'ini',
            'and', 'but', 'or', 'because', 'if', 'when', 'that', 'which', 
            'with', 'for', 'to', 'the', 'a', 'an', 'they', 'it', 'this'
        ]
        if last_word in incomplete_indicators:
            score -= 10  # Strongly penalize - definitely mid-sentence
    
    return score

def _find_best_ending_phrase(phrases, min_end_time, max_end_time, prefer_within_range=True):
    """
    Find the best phrase to end on within a time range.
    Prioritizes phrases with good closure scores.
    """
    candidates = []
    
    for p in phrases:
        # Phrase must end after min_end_time
        if p['end'] < min_end_time:
            continue
        
        # Calculate if it's within preferred range
        within_range = p['end'] <= max_end_time
        
        closure_score = _get_closure_score(p['text'])
        
        # Bonus for being within the original range
        range_bonus = 5 if within_range else 0
        
        # Penalty for going too far beyond (but allow some extension for good endings)
        extension = max(0, p['end'] - max_end_time)
        extension_penalty = min(extension * 0.5, 10)  # Max 10 point penalty
        
        total_score = closure_score + range_bonus - extension_penalty
        
        candidates.append({
            'phrase': p,
            'score': total_score,
            'closure_score': closure_score,
            'extension': extension,
            'text_preview': p['text'][-40:] if len(p['text']) > 40 else p['text']
        })
    
    if not candidates:
        return None
    
    # Sort by score (highest first), then by smallest extension
    candidates.sort(key=lambda c: (-c['score'], c['extension']))
    
    best = candidates[0]
    
    # If best score is still negative, we need to find a better ending
    # Look for the PREVIOUS phrase that ends cleanly
    if best['score'] < 0:
        # Find phrases with positive closure scores (actually end with punctuation)
        good_endings = [c for c in candidates if c['closure_score'] >= 8]
        
        if good_endings:
            # Use the first good ending (closest to original end)
            chosen = min(good_endings, key=lambda c: abs(c['phrase']['end'] - max_end_time))
            return chosen['phrase']
    
    return best['phrase']

def snap_to_phrase_boundaries(clips_data, phrase_timings, min_duration=30):
    """
    Adjust clip boundaries to align with SENTENCE endings.
    """
    if not clips_data or not phrase_timings:
        return clips_data
    
    sorted_phrases = sorted(phrase_timings, key=lambda p: p['start'])
    is_auto = (min_duration == "auto")
    target_min_duration = 30 if is_auto else int(min_duration)
    
    adjusted_clips = []
    
    for clip in clips_data:
        original_start = clip['start_time']
        original_end = clip['end_time']
        
        overlapping_phrases = [
            p for p in sorted_phrases 
            if p['end'] > original_start and p['start'] < original_end
        ]
        
        if not overlapping_phrases:
            adjusted_clips.append(clip)
            continue
        
        first_phrase = min(overlapping_phrases, key=lambda p: p['start'])
        new_start = first_phrase['start']
        
        max_extension = 10.0
        phrases_from_start = [p for p in sorted_phrases if p['start'] >= new_start]
        
        best_ending = _find_best_ending_phrase(
            phrases_from_start,
            min_end_time=new_start + target_min_duration - 5,
            max_end_time=original_end + max_extension
        )
        
        if best_ending:
            new_end = best_ending['end']
            ending_text = best_ending['text'][-30:] if len(best_ending['text']) > 30 else best_ending['text']
        else:
            last_phrase = max(overlapping_phrases, key=lambda p: p['end'])
            new_end = last_phrase['end']
            ending_text = "fallback"
        
        current_duration = new_end - new_start
        safety_min = target_min_duration
        
        if current_duration < safety_min:
            phrases_after = [p for p in sorted_phrases if p['start'] >= new_end]
            
            for next_phrase in phrases_after:
                potential_end = next_phrase['end']
                if potential_end - new_start >= safety_min:
                    if _get_closure_score(next_phrase['text']) >= 5:
                        new_end = potential_end
                        break
                    elif potential_end - new_start >= safety_min + 5:
                        new_end = potential_end
                        break
        
        adjusted_clip = clip.copy()
        adjusted_clip['start_time'] = new_start
        adjusted_clip['end_time'] = new_end
        
        if new_start != original_start or new_end != original_end:
            # closure_score = _get_closure_score(best_ending['text']) if best_ending else 0
            # Logging if needed
            pass
        
        adjusted_clips.append(adjusted_clip)
    
    return adjusted_clips
