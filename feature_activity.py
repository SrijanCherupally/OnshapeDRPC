"""Interpret only the open feature editor, never toolbar or feature-list text."""
import re
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

LABELS = {
    'sketch': 'Sketch', 'sketchtools': 'Sketch', 'extrude': 'Extrude', 'revolve': 'Revolve', 'sweep': 'Sweep',
    'loft': 'Loft', 'fillet': 'Fillet', 'chamfer': 'Chamfer', 'shell': 'Shell',
    'draft': 'Draft', 'hole': 'Hole', 'mirror': 'Mirror', 'transform': 'Transform',
    'boolean': 'Boolean', 'split': 'Split', 'thicken': 'Thicken', 'enclose': 'Enclose',
    'linearpattern': 'Linear Pattern', 'circularpattern': 'Circular Pattern',
    'curvepattern': 'Curve Pattern', 'faceblend': 'Face Blend', 'deleteface': 'Delete Face',
    'moveface': 'Move Face', 'replaceface': 'Replace Face', 'offsetsurface': 'Offset Surface',
    'derived': 'Derived', 'variable': 'Variable', 'mateconnector': 'Mate Connector',
    'sheetmetal': 'Sheet Metal', 'sheetmetalmodel': 'Sheet Metal', 'rib': 'Rib',
    'wrap': 'Wrap', 'helix': 'Helix', 'plane': 'Plane', 'frame': 'Frame',
}


for _name in json.loads((Path(__file__).resolve().parent / 'assets/onshape-icons/sources.json').read_text(encoding='utf-8')):
    if _name not in {'Onshape', 'Assembly'}:
        LABELS.setdefault(re.sub(r'[^a-z]', '', _name.casefold()), _name.title().replace('Pcb', 'PCB'))


def feature_activity(observation):
    if not observation.get('available') or not observation.get('part_studio'):
        return {'label': 'Unavailable', 'name': ''}
    editor = observation.get('feature')
    if editor is None:
        return {'label': 'Idle', 'name': ''}
    if not isinstance(editor, dict):
        return {'label': 'Feature', 'name': ''}
    name = str(editor.get('name', '')).strip()[:128]
    link = urlparse(str(editor.get('help_url', '')))
    topic = ''
    if link.hostname == 'cad.onshape.com' and link.path.startswith('/help/'):
        topic = parse_qs(link.fragment).get('cshid', [''])[0]
        if not topic:
            topic = link.path.rsplit('/', 1)[-1].split('.')[0]
    label = LABELS.get(re.sub(r'[^a-z]', '', topic.casefold()))
    if not label:
        base = re.sub(r'\s+\d+$', '', name).casefold()
        label = LABELS.get(re.sub(r'[^a-z]', '', base), 'Feature')
    return {'label': label, 'name': name}
