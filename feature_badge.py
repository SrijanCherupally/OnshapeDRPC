"""Local feature artwork; contains no model image and needs no Onshape requests."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


@lru_cache(maxsize=64)
def feature_badge(label):
    image = Image.new('RGB', (300, 300), (43, 45, 49))
    draw = ImageDraw.Draw(image)
    green = (109, 190, 68)
    white = (235, 237, 239)
    if label == 'Idle':
        draw.ellipse((92, 51, 208, 167), outline=green, width=9)
        draw.line((150, 74, 150, 111, 177, 128), fill=white, width=9)
    elif label == 'Sketch':
        draw.rounded_rectangle((76, 55, 205, 172), radius=8, outline=green, width=7)
        draw.line((103, 142, 184, 68), fill=white, width=14)
        draw.polygon([(96, 149), (101, 129), (115, 142)], fill=white)
    elif label == 'Extrude':
        draw.polygon([(84, 93), (150, 59), (215, 93), (150, 129)], fill=green)
        draw.polygon([(84, 93), (150, 129), (150, 185), (84, 149)], outline=white, width=5)
        draw.polygon([(150, 129), (215, 93), (215, 149), (150, 185)], outline=white, width=5)
        draw.line((150, 49, 150, 23), fill=white, width=6)
        draw.polygon([(137, 35), (150, 17), (163, 35)], fill=white)
    else:
        draw.rounded_rectangle((86, 58, 214, 172), radius=16, outline=green, width=8)
        for y in (87, 116, 145):
            draw.line((113, y, 188, y), fill=white, width=6)
            draw.ellipse((98, y-4, 106, y+4), fill=green)
    words = ['Detection', 'Unavailable'] if label == 'Unavailable' else label.split()
    size = 30 if max(map(len, words)) > 10 else 36
    font = ImageFont.load_default(size=size)
    for path in (Path('C:/Windows/Fonts/seguisb.ttf'), Path('C:/Windows/Fonts/segoeui.ttf')):
        if path.exists():
            font = ImageFont.truetype(str(path), size)
            break
    for index, word in enumerate(words):
        draw.text((150, 213 + index*39), word, font=font, fill=white, anchor='mm')
    output = BytesIO()
    image.save(output, 'PNG')
    return output.getvalue()
