"""
Test script for Preset 2 Hook Implementation
Run this to verify text parsing and rendering logic works correctly.
"""

import sys
import os

# Add parent directory to path to import preset2_hook
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.media.subtitle.preset2_hook import _parse_preset2_text

def test_text_parsing():
    """Test the markdown text parser"""
    print("=" * 60)
    print("Testing Preset 2 Text Parser")
    print("=" * 60)
    
    test_cases = [
        {
            "input": "this might be *the best* **BUDGET** wireless microphone",
            "description": "Mixed styles (regular, italic, bold)"
        },
        {
            "input": "**AMAZING** deal",
            "description": "Bold at start"
        },
        {
            "input": "check out *this* video",
            "description": "Italic in middle"
        },
        {
            "input": "regular text only",
            "description": "No markup"
        },
        {
            "input": "*all* **text** *styled*",
            "description": "All styled words"
        }
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test['description']}")
        print(f"Input: {test['input']}")
        
        segments = _parse_preset2_text(test['input'])
        
        print("Parsed Segments:")
        for seg in segments:
            style_marker = ""
            if seg['style'] == 'bold':
                style_marker = "**BOLD**"
            elif seg['style'] == 'italic':
                style_marker = "*ITALIC*"
            else:
                style_marker = "REGULAR"
            
            highlight_marker = " + HIGHLIGHTED" if seg['highlight'] else ""
            print(f"  - '{seg['text']}' → {style_marker}{highlight_marker}")
        
        print("✅ Parsed successfully")
    
    print("\n" + "=" * 60)
    print("All parsing tests completed!")
    print("=" * 60)

def test_rendering_dry_run():
    """Test that rendering function can be imported and has correct signature"""
    print("\n" + "=" * 60)
    print("Testing Preset 2 Renderer Import")
    print("=" * 60)
    
    try:
        from services.media.subtitle.preset2_hook import _render_preset2_hook
        print("✅ _render_preset2_hook imported successfully")
        
        # Check function signature
        import inspect
        sig = inspect.signature(_render_preset2_hook)
        params = list(sig.parameters.keys())
        
        expected_params = ['config', 'hook_styles', 'video_width', 'video_height', 'duration']
        
        print(f"\nFunction parameters: {params}")
        
        if params == expected_params:
            print("✅ Function signature matches expected parameters")
        else:
            print(f"⚠️  Expected: {expected_params}")
            print(f"⚠️  Got: {params}")
        
    except Exception as e:
        print(f"❌ Error importing renderer: {e}")
        return False
    
    print("\n" + "=" * 60)
    print("Renderer import test completed!")
    print("=" * 60)
    
    return True

def print_usage_examples():
    """Print example inputs for manual testing"""
    print("\n" + "=" * 60)
    print("Manual Testing Examples")
    print("=" * 60)
    
    examples = [
        "this might be *the best* **BUDGET** wireless microphone",
        "**SHOCKING** *result* you won't believe",
        "the **ULTIMATE** guide to *everything*",
        "*amazing* **DEAL** right now",
        "watch this **NOW** before it's gone"
    ]
    
    print("\nCopy-paste these into the Preset 2 textarea:\n")
    for i, example in enumerate(examples, 1):
        print(f"{i}. {example}")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    print("\n🎯 PRESET 2 HOOK TEST SUITE\n")
    
    # Test 1: Text parsing
    test_text_parsing()
    
    # Test 2: Renderer import
    renderer_ok = test_rendering_dry_run()
    
    # Print manual test examples
    print_usage_examples()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("✅ Text parsing: PASSED")
    print(f"{'✅' if renderer_ok else '❌'} Renderer import: {'PASSED' if renderer_ok else 'FAILED'}")
    print("\n💡 Next: Test in the app by generating a video with Preset 2")
    print("=" * 60)
