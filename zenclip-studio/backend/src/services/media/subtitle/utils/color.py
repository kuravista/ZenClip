def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple"""
    if not isinstance(hex_color, str):
        return hex_color
        
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
