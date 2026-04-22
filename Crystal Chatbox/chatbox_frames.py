"""
Chatbox Frame System
Adds customizable visual frames/outlines around chatbox messages
Note: VRChat has limited Unicode support - only use ASCII and basic characters
"""

FRAME_STYLES = {
    "none": {
        "name": "None",
        "description": "No frame, plain text",
        "top_left": "",
        "top_right": "",
        "bottom_left": "",
        "bottom_right": "",
        "horizontal": "",
        "vertical": "",
        "padding": False
    },
    "dots": {
        "name": "Dots",
        "description": "Simple dotted border",
        "top_left": ".",
        "top_right": ".",
        "bottom_left": ".",
        "bottom_right": ".",
        "horizontal": ".",
        "vertical": ".",
        "padding": True
    },
    "dashes": {
        "name": "Dashes",
        "description": "Clean dash border",
        "top_left": "+",
        "top_right": "+",
        "bottom_left": "+",
        "bottom_right": "+",
        "horizontal": "-",
        "vertical": "|",
        "padding": True
    },
    "equals": {
        "name": "Equals",
        "description": "Double line style",
        "top_left": "+",
        "top_right": "+",
        "bottom_left": "+",
        "bottom_right": "+",
        "horizontal": "=",
        "vertical": "|",
        "padding": True
    },
    "stars": {
        "name": "Stars",
        "description": "Decorative star border",
        "top_left": "*",
        "top_right": "*",
        "bottom_left": "*",
        "bottom_right": "*",
        "horizontal": "*",
        "vertical": "*",
        "padding": True
    },
    "hashtags": {
        "name": "Hashtags",
        "description": "Bold hashtag border",
        "top_left": "#",
        "top_right": "#",
        "bottom_left": "#",
        "bottom_right": "#",
        "horizontal": "#",
        "vertical": "#",
        "padding": True
    },
    "tildes": {
        "name": "Tildes",
        "description": "Wavy tilde border",
        "top_left": "~",
        "top_right": "~",
        "bottom_left": "~",
        "bottom_right": "~",
        "horizontal": "~",
        "vertical": "~",
        "padding": True
    },
    "minimal_top": {
        "name": "Minimal Top",
        "description": "Simple line above text",
        "top_left": "",
        "top_right": "",
        "bottom_left": "",
        "bottom_right": "",
        "horizontal": "-",
        "vertical": "",
        "top_only": True,
        "padding": False
    },
    "minimal_both": {
        "name": "Minimal Lines",
        "description": "Lines above and below",
        "top_left": "",
        "top_right": "",
        "bottom_left": "",
        "bottom_right": "",
        "horizontal": "-",
        "vertical": "",
        "top_only": False,
        "padding": False
    },
    "arrows": {
        "name": "Arrows",
        "description": "Arrow-style accents",
        "top_left": ">",
        "top_right": "<",
        "bottom_left": ">",
        "bottom_right": "<",
        "horizontal": "-",
        "vertical": "|",
        "padding": True
    },
    "brackets": {
        "name": "Brackets",
        "description": "Clean bracket style",
        "top_left": "[",
        "top_right": "]",
        "bottom_left": "[",
        "bottom_right": "]",
        "horizontal": "",
        "vertical": "",
        "bracket_mode": True,
        "padding": False
    },
    "parens": {
        "name": "Parentheses",
        "description": "Soft parentheses style",
        "top_left": "(",
        "top_right": ")",
        "bottom_left": "(",
        "bottom_right": ")",
        "horizontal": "",
        "vertical": "",
        "bracket_mode": True,
        "padding": False
    },
    "angle": {
        "name": "Angle Brackets",
        "description": "Sharp angle style",
        "top_left": "<",
        "top_right": ">",
        "bottom_left": "<",
        "bottom_right": ">",
        "horizontal": "",
        "vertical": "",
        "bracket_mode": True,
        "padding": False
    },
    "pipes": {
        "name": "Pipes",
        "description": "Vertical pipe style",
        "top_left": "|",
        "top_right": "|",
        "bottom_left": "|",
        "bottom_right": "|",
        "horizontal": "",
        "vertical": "",
        "bracket_mode": True,
        "padding": False
    }
}


def get_frame_styles():
    """Return list of available frame styles for UI"""
    return [{"id": k, "name": v["name"], "description": v["description"]} for k, v in FRAME_STYLES.items()]


def get_longest_line_length(text):
    """Get the length of the longest line in text"""
    lines = text.split('\n')
    return max(len(line) for line in lines) if lines else 0


def apply_frame(text, style_id, width=None):
    """
    Apply a frame style to text
    
    Args:
        text: The message text to frame
        style_id: The frame style identifier
        width: Optional fixed width (auto-calculated if None)
    
    Returns:
        Framed text string
    """
    if not text or not text.strip():
        return text
    
    style = FRAME_STYLES.get(style_id, FRAME_STYLES["none"])
    
    if style_id == "none":
        return text
    
    lines = text.split('\n')
    
    if width is None:
        width = get_longest_line_length(text)
    
    width = min(width, 40)
    
    if style.get("bracket_mode"):
        return apply_bracket_frame(lines, style, width)
    
    if style.get("top_only") is not None:
        return apply_minimal_frame(lines, style, width)
    
    return apply_box_frame(lines, style, width)


def truncate_line(line, max_width):
    """Truncate a line to fit within max_width, adding ellipsis if needed"""
    if len(line) <= max_width:
        return line
    if max_width <= 3:
        return line[:max_width]
    return line[:max_width-1] + "..."


def apply_box_frame(lines, style, width):
    """Apply a full box frame around text"""
    tl = style["top_left"]
    tr = style["top_right"]
    bl = style["bottom_left"]
    br = style["bottom_right"]
    h = style["horizontal"]
    v = style["vertical"]
    
    inner_width = width + 2
    
    result = []
    
    top_line = tl + (h * inner_width) + tr
    result.append(top_line)
    
    for line in lines:
        truncated = truncate_line(line, width)
        padded = truncated.ljust(width)
        if style["padding"]:
            result.append(f"{v} {padded} {v}")
        else:
            result.append(f"{v}{padded}{v}")
    
    bottom_line = bl + (h * inner_width) + br
    result.append(bottom_line)
    
    return '\n'.join(result)


def apply_minimal_frame(lines, style, width):
    """Apply minimal lines above/below text"""
    h = style["horizontal"]
    top_only = style.get("top_only", False)
    
    line_str = h * (width + 4)
    
    result = []
    result.append(line_str)
    
    for line in lines:
        truncated = truncate_line(line, width)
        result.append(f"  {truncated}  ")
    
    if not top_only:
        result.append(line_str)
    
    return '\n'.join(result)


def apply_bracket_frame(lines, style, width=40):
    """Apply bracket-style framing to each line"""
    tl = style["top_left"]
    tr = style["top_right"]
    
    result = []
    for line in lines:
        truncated = truncate_line(line, width)
        result.append(f"{tl}{truncated}{tr}")
    
    return '\n'.join(result)


def get_frame_preview(style_id):
    """Generate a preview of the frame style"""
    sample_text = "Hello World\n12:00 PM"
    return apply_frame(sample_text, style_id)
