"""Display bundled Onshape icons; no model content or network requests."""
from functools import lru_cache
from io import BytesIO
import json
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

ASSETS = Path(__file__).resolve().parent / 'assets' / 'onshape-icons'
SOURCES = json.loads((ASSETS / 'sources.json').read_text(encoding='utf-8'))
ICONS = {re.sub(r'[^a-z0-9]', '', name.casefold()): item['file'] for name, item in SOURCES.items()}
ICONS['sheetmetal'] = ICONS['sheetmetalmodel']
ICONS['viewing'] = ICONS['partstudio']


@lru_cache(maxsize=128)
def static_badge_url(label, compact=False):
    manifest = json.loads((ASSETS.parent / 'presence-cards/cards.json').read_text(encoding='utf-8'))
    key = re.sub(r'[^a-z0-9]', '', label.casefold())
    card = manifest.get(key, manifest['feature'])
    filename = card['compact' if compact else 'full']
    return 'https://raw.githubusercontent.com/SrijanCherupally/OnshapeDRPC/main/assets/presence-cards/' + filename


@lru_cache(maxsize=128)
def feature_badge(label, compact=False):
    scale = 1024 / 300
    def box(values):
        return tuple(round(v * scale) for v in values)
    image = Image.new('RGBA', (1024, 1024), (37, 40, 45, 255))
    draw = ImageDraw.Draw(image)
    key = re.sub(r'[^a-z0-9]', '', label.casefold())
    filename = ICONS.get(key, ICONS['onshape'])
    branded = filename == ICONS['onshape']
    if branded:
        draw.ellipse(box((35, 12, 265, 242)), fill=(38, 53, 43), outline=(79, 121, 70), width=round(scale))
        area, top = (190, 190), 28
    elif compact:
        draw.rounded_rectangle(box((12, 12, 288, 288)), radius=round(48*scale), fill=(242, 245, 247), outline=(192, 207, 192), width=round(scale))
        area, top = (232, 232), 34
    else:
        draw.rounded_rectangle(box((40, 24, 260, 226)), radius=round(32*scale), fill=(242, 245, 247), outline=(192, 207, 192), width=round(scale))
        area, top = (164, 164), 40
    with Image.open(ASSETS / filename) as source:
        icon = source.convert('RGBA')
        bounds = icon.getchannel('A').getbbox()
        if bounds:
            icon = icon.crop(bounds)
        area = box(area)
        icon = ImageOps.contain(icon, area, Image.Resampling.LANCZOS)
        icon = icon.filter(ImageFilter.UnsharpMask(radius=1.5*scale, percent=95, threshold=4))
        image.alpha_composite(icon, ((1024-icon.width)//2, round(top*scale)+(area[1]-icon.height)//2))
    if not compact:
        caption = 'Part Studio' if label == 'Viewing' else 'Onshape' if label == 'Unavailable' else label
        size = round(31*scale)
        font_path = None
        for path in (Path('C:/Windows/Fonts/seguisb.ttf'), Path('C:/Windows/Fonts/segoeui.ttf')):
            if path.exists():
                font_path = str(path)
                break
        while True:
            font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default(size=size)
            if draw.textlength(caption, font=font) <= 260*scale or size <= 16*scale:
                break
            size -= 1
        draw.text(box((150, 263)), caption, font=font, fill=(235, 237, 239), anchor='mm')
    output = BytesIO()
    image.convert('RGB').save(output, 'PNG')
    return output.getvalue()
