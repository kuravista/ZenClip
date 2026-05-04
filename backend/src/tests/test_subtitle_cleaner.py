
import sys
import os
import json

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock
sys.modules['faster_whisper'] = MagicMock()
sys.modules['services.core.binary_manager'] = MagicMock()
sys.modules['services.core.resource_monitor'] = MagicMock()

from services.media.audio_transcriber import clean_repetitive_content, clean_phrase_level_repetition

def test_cleaner():
    # Simulate a user-edited transcript
    # User changed "foo foo" to "foo bar" for example
    # Or user just fixed a typo
    
    original_edit = [
        {
            "text": "Hello world.",
            "start": 0.0,
            "end": 2.0,
            "words": [
                {"text": "Hello", "start": 0.0, "end": 1.0},
                {"text": "world.", "start": 1.0, "end": 2.0}
            ]
        },
        {
            "text": "This is a manual fix.",
            "start": 2.5,
            "end": 4.0,
            "words": [
                {"text": "This", "start": 2.5, "end": 2.8},
                {"text": "is", "start": 2.8, "end": 3.0},
                {"text": "a", "start": 3.0, "end": 3.2},
                {"text": "manual", "start": 3.2, "end": 3.6},
                {"text": "fix.", "start": 3.6, "end": 4.0}
            ]
        },
        # Simulate a slight repetition that might trigger logic
        {
            "text": "No no no.",
            "start": 5.0,
            "end": 6.0,
            "words": [
                {"text": "No", "start": 5.0, "end": 5.3},
                {"text": "no", "start": 5.3, "end": 5.6},
                {"text": "no.", "start": 5.6, "end": 5.9}
            ]
        }
    ]
    
    print("Original:", json.dumps(original_edit, indent=2))
    
    cleaned_1 = clean_repetitive_content(original_edit)
    cleaned_2 = clean_phrase_level_repetition(cleaned_1)
    
    print("\nCleaned:", json.dumps(cleaned_2, indent=2))
    
    # Check if "No no no" was preserved (max_repeats default is 3)
    # Check if "manual fix" is preserved
    
    # Test strict repetition
    repetition_case = [
        {
            "text": "Test Test Test Test", 
            "start": 0, "end": 1,
            "words": [
                 {"text": "Test", "start": 0, "end": 0.2},
                 {"text": "Test", "start": 0.2, "end": 0.4},
                 {"text": "Test", "start": 0.4, "end": 0.6},
                 {"text": "Test", "start": 0.6, "end": 0.8}
            ]
        }
    ]
    # Test Fuzzy Repetition (Production Grade Check)
    fuzzy_case = [
        {
            "text": "keren keren. keren!", 
            "start": 0, "end": 1,
            "words": [
                 {"text": "keren", "start": 0, "end": 0.2},
                 {"text": "keren.", "start": 0.2, "end": 0.4},
                 {"text": "keren!", "start": 0.4, "end": 0.6}
            ]
        }
    ]
    print("\nFuzzy Case Before:", json.dumps(fuzzy_case, indent=2))
    cleaned_fuzzy = clean_repetitive_content(fuzzy_case)
    print("Fuzzy Case After:", json.dumps(cleaned_fuzzy, indent=2))
    
    # Test Phrase Level Fuzzy Loop
    phrase_loop = [
        {"text": "This is a test.", "start": 0.0, "end": 1.0},
        {"text": "This is a test", "start": 1.1, "end": 2.0}, # No dot, should match
        {"text": "This is a test.", "start": 2.1, "end": 3.0},
        {"text": "New sentence.", "start": 10.0, "end": 12.0} # Large gap, should keep
    ]
    print("\nPhrase Loop Before:", json.dumps(phrase_loop, indent=2))
    cleaned_phrase_loop = clean_phrase_level_repetition(phrase_loop)
    print("Phrase Loop After:", json.dumps(cleaned_phrase_loop, indent=2))

if __name__ == "__main__":
    test_cleaner()
