import re

def generate_fallback_smart_metadata(text):
    """
    Generate basic highlight and emoji maps based on keyword matching
    if the LLM fails to return them.
    """
    text_lower = text.lower()
    
    # Common viral keywords mapping
    keywords = {
        'uang': {'color': '#00FF00', 'emoji': ''},
        'kaya': {'color': '#FFD700', 'emoji': ''},
        'miskin': {'color': '#808080', 'emoji': ''},
        'sukses': {'color': '#00FFFF', 'emoji': ''},
        'gagal': {'color': '#FF0000', 'emoji': ''},
        'bahaya': {'color': '#FF0000', 'emoji': ''},
        'penting': {'color': '#FFFF00', 'emoji': ''},
        'rahasia': {'color': '#8A2BE2', 'emoji': ''},
        'cinta': {'color': '#FF69B4', 'emoji': ''},
        'mati': {'color': '#000000', 'emoji': ''},
        'hidup': {'color': '#FFFFFF', 'emoji': ''},
        'cepat': {'color': '#FFA500', 'emoji': ''},
        'lambat': {'color': '#808080', 'emoji': ''},
        'besar': {'color': '#FF00FF', 'emoji': ''},
        'kecil': {'color': '#00FF00', 'emoji': ''},
        'senang': {'color': '#FFFF00', 'emoji': ''},
        'sedih': {'color': '#0000FF', 'emoji': ''},
        'marah': {'color': '#FF0000', 'emoji': ''},
        'takut': {'color': '#800080', 'emoji': ''},
        'viral': {'color': '#FF00FF', 'emoji': ''}
    }
    
    highlight_map = {}
    emoji_map = {}
    
    # Simple word tokenization
    words = re.findall(r'\w+', text_lower)
    
    # Find up to 5 keywords
    found_count = 0
    for word in words:
        if word in keywords and found_count < 5:
            # Add to maps
            highlight_map[word] = keywords[word]['color']
            emoji_map[word] = keywords[word]['emoji']
            found_count += 1
            
    return highlight_map, emoji_map
