"""Display bundled Onshape icons; no model content or network requests."""
from functools import lru_cache
from io import BytesIO
import json
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont, ImageOps

ASSETS = Path(__file__).resolve().parent / 'assets' / 'onshape-icons'
SOURCES = json.loads((ASSETS / 'sources.json').read_text(encoding='utf-8'))
ICONS = {re.sub(r'[^a-z0-9]', '', name.casefold()): item['file'] for name, item in SOURCES.items()}
ICONS['sheetmetal'] = ICONS['sheetmetalmodel']


@lru_cache(maxsize=128)
def feature_badge(label, compact=False):
    image = Image.new('RGBA', (300, 300), (43, 45, 49, 255))
    draw = ImageDraw.Draw(image)
    key = re.sub(r'[^a-z0-9]', '', label.casefold())
    filename = ICONS.get(key, ICONS['onshape'])
    branded = filename == ICONS['onshape']
    if branded:
        draw.ellipse((33, 7, 267, 241), fill=(40, 55, 45), outline=(58, 83, 60), width=2)
        area, top = (190, 190), 28
    elif compact:
        draw.rounded_rectangle((12, 12, 288, 288), radius=42, fill=(239, 242, 245))
        area, top = (232, 232), 34
    else:
        draw.rounded_rectangle((42, 22, 258, 222), radius=28, fill=(239, 242, 245))
        area, top = (164, 164), 40
    with Image.open(ASSETS / filename) as source:
        icon = source.convert('RGBA')
        bounds = icon.getchannel('A').getbbox()
        if bounds:
            icon = icon.crop(bounds)
        icon = ImageOps.contain(icon, area, Image.Resampling.LANCZOS)
        image.alpha_composite(icon, ((300-icon.width)//2, top+(area[1]-icon.height)//2))
    if not compact:
        caption = 'Onshape' if label == 'Unavailable' else label
        size = 33
        font_path = None
        for path in (Path('C:/Windows/Fonts/seguisb.ttf'), Path('C:/Windows/Fonts/segoeui.ttf')):
            if path.exists():
                font_path = str(path)
                break
        while True:
            font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default(size=size)
            if draw.textlength(caption, font=font) <= 264 or size <= 16:
                break
            size -= 1
        draw.text((150, 260), caption, font=font, fill=(235, 237, 239), anchor='mm')
    output = BytesIO()
    image.convert('RGB').save(output, 'PNG')
    return output.getvalue()
