import re
import os
from services.ai.llm_provider import generate_llm_response

def detect_video_genre(transcript_text, api_key=None, api_provider='deepseek'):
    """
    Detect the genre of the video based on the transcript.
    Returns one of: 'general', 'podcast', 'gaming', 'motivational', 'comedy', 'education'
    """
    try:
        # Take a sample of the transcript (first 5000 chars) to avoid huge context
        sample_text = transcript_text[:5000]
        
        prompt = f"""
        Analisis transkrip video berikut dan tentukan GENRE utamanya.
        Pilih SATU dari kategori berikut:
        - podcast (jika ada dialog/wawancara 2 orang atau lebih)
        - gaming (jika tentang game, gameplay, istilah game)
        - motivational (jika berisi nasihat hidup, inspirasi, speech)
        - comedy (jika lucu, standup, sketsa, parodi)
        - education (jika tutorial, fakta, penjelasan topik, sejarah, sains)
        - general (jika tidak masuk kategori di atas atau vlog umum)

        TRANSKRIP:
        {sample_text}

        Output HANYA satu kata kategori (huruf kecil).
        """
        
        print(f"[INFO] Auto-detecting video genre with {api_provider.upper()}...")
        
        detected_genre = generate_llm_response(
            prompt=prompt,
            system_instruction="You are a video content classifier. Return only the category name.",
            api_key=api_key or os.environ.get('DEEPSEEK_API_KEY'),
            provider=api_provider
        )
        
        detected_genre = detected_genre.strip().lower()
        
        # Clean up response (remove punctuation etc)
        detected_genre = re.sub(r'[^a-z]', '', detected_genre)
        
        valid_genres = ['podcast', 'gaming', 'motivational', 'comedy', 'education', 'general']
        if detected_genre not in valid_genres:
            print(f"[WARN] Detected genre '{detected_genre}' not in list. Defaulting to 'general'.")
            return 'general'
            
        print(f"[SUCCESS] Detected genre: {detected_genre.capitalize()}")
        return detected_genre
        
    except Exception as e:
        print(f"[ERROR] Error detecting genre: {str(e)}. Defaulting to 'general'.")
        return 'general'
