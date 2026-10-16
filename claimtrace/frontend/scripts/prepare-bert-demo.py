"""Build local full-paper fixtures from the official BERT PDF and parser layout JSON.

Usage: python prepare-bert-demo.py --pdf bert.pdf --layout bert.json
Run the repository's opendataloader-pdf converter in local mode to get layout JSON.
"""
import argparse
import hashlib
import html
import json
import re
import shutil
import unicodedata
from pathlib import Path

import pymupdf

args = argparse.ArgumentParser()
args.add_argument('--pdf', type=Path, required=True)
args.add_argument('--layout', type=Path, required=True)
opts = args.parse_args()
root = Path(__file__).resolve().parents[1] / 'src/assets/demo'
root.mkdir(parents=True, exist_ok=True)
pdf = pymupdf.open(opts.pdf)
layout = json.loads(opts.layout.read_text())
# Whole visual regions prevent the parser's tiny vector fragments from appearing
# as separate figures, and preserve every original results table.
regions = [
    (3, 'Figure 1', (72, 57, 526, 246), 'bert-pretraining-finetuning.png'),
    (5, 'Figure 2', (72, 58, 526, 177), 'bert-input-representation.png'),
    (6, 'Table 1', (72, 55, 526, 159), 'bert-table-1.png'),
    (7, 'Table 2', (72, 58, 291, 245), 'bert-table-2.png'),
    (7, 'Table 3', (72, 295, 291, 438), 'bert-table-3.png'),
    (7, 'Table 4', (307, 61, 526, 170), 'bert-table-4.png'),
    (8, 'Table 5', (72, 59, 292, 149), 'bert-table-5.png'),
    (9, 'Table 6', (72, 598, 291, 708), 'bert-table-6.png'),
    (9, 'Table 7', (307, 59, 526, 232), 'bert-table-7.png'),
    (13, 'Figure 3', (72, 58, 526, 177), 'bert-figure-3.png'),
    (15, 'Figure 4', (105, 57, 492, 442), 'bert-figure-4.png'),
    (16, 'Figure 5', (72, 565, 291, 708), 'bert-figure-5.png'),
    (16, 'Table 8', (307, 178, 526, 300), 'bert-table-8.png'),
]
for page, label, rect, name in regions:
    pdf[page - 1].get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=pymupdf.Rect(*rect), alpha=False).save(root / name)
shutil.copyfile(opts.pdf, root / 'bert-naacl2019.pdf')

def clean(value):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value)).strip()

def children(node):
    if node.get('type') == 'list':
        for child in node.get('list items', []):
            yield from children(child)
    elif node.get('content'):
        yield node
    else:
        for child in node.get('kids', []):
            yield from children(child)

# Rejoin parser fragments across columns and page breaks. Keep the location of
# the first fragment, and leave footnotes/captions/visual regions independent.
previous_body = None
for top in layout['kids']:
    for node in children(top):
        page_number = node.get('page number', top.get('page number'))
        box = node.get('bounding box')
        if box and page_number:
            x0, y0, x1, y1 = box
            rect = pymupdf.Rect(x0, pdf[page_number - 1].rect.height - y1, x1, pdf[page_number - 1].rect.height - y0)
            if any(region[0] == page_number and rect.get_area() and
                   (rect & pymupdf.Rect(*region[2])).get_area() / rect.get_area() > .5
                   for region in regions):
                continue
        text = clean(node.get('content', ''))
        if node.get('type') == 'heading':
            previous_body = None
            continue
        if node.get('font size', 0) < 10.5 or re.match(r'^(Figure|Table) \d+:', text):
            continue
        if previous_body and previous_body.get('type') != 'list item' and text and not text.startswith('•'):
            before = clean(previous_body['content'])
            if not re.search(r'[.!?:][”"\d]*$', before):
                previous_body['content'] = before[:-1] + text if before.endswith('-') else before + ' ' + text
                node['content'] = ''
                continue
        previous_body = node

# Obtain the real superscript markers from PDF span flags, rather than inventing
# numeric citation markers for this author-year paper.
markers = {}
for page_number, page in enumerate(pdf, 1):
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            spans = line['spans']
            for i, span in enumerate(spans):
                if span['flags'] & 1 and span['text'].strip().isdigit() and i:
                    previous = clean(spans[i - 1]['text'])
                    if len(previous) > 3:
                        markers.setdefault(page_number, []).append((previous, span['text'].strip()))

claim_text = 'BERT’s model architecture is a multi-layer bidirectional Transformer encoder based on the original implementation described in Vaswani et al. (2017) and released in the tensor2tensor library.'
pages = []
rich_parts = []
rich_locations = {}
claim_location = None
for page_number in range(1, len(pdf) + 1):
    page_regions = [region for region in regions if region[0] == page_number]
    emitted = set()
    paragraphs = []
    parts = []

    def image(region):
        _, label, _, filename = region
        emitted.add(filename)
        parts.append(f'![BERT original {label}, PDF page {page_number}]({filename})')

    for top in layout['kids']:
        if top.get('page number') != page_number:
            continue
        for node in children(top):
            text = clean(node.get('content', ''))
            if not text:
                continue
            box = node.get('bounding box')
            if box:
                x0, y0, x1, y1 = box
                node_rect = pymupdf.Rect(x0, pdf[page_number - 1].rect.height - y1, x1, pdf[page_number - 1].rect.height - y0)
                overlaps = [region for region in page_regions if node_rect.get_area() and (node_rect & pymupdf.Rect(*region[2])).get_area() / node_rect.get_area() > .5]
                if overlaps:
                    for region in overlaps:
                        if region[3] not in emitted:
                            image(region)
                    continue
            for region in page_regions:
                if region[3] not in emitted and text.startswith(region[1] + ':'):
                    image(region)
            if node.get('type') == 'heading':
                if page_number == 1 and text == clean(pdf.metadata['title']):
                    continue  # The same original title is already the outer H1.
                parts.append(f'### {html.escape(text, quote=False)}')
                continue
            split_texts = [text]
            if claim_text in text:
                before, after = text.split(claim_text, 1)
                if before.strip():
                    parts.append('### ' + before.strip())
                split_texts = [claim_text + ('1' if after.startswith('1') else ''), after.removeprefix('1').strip()]
            for paragraph in split_texts:
                if not paragraph:
                    continue
                index = len(paragraphs)
                if claim_text in paragraph:
                    claim_location = {'page': page_number, 'paragraph_index': index}
                paragraphs.append(paragraph)
                markdown = html.escape(paragraph, quote=False)
                for previous, marker in markers.get(page_number, []):
                    needle = html.escape(previous, quote=False) + marker
                    markdown = markdown.replace(needle, html.escape(previous, quote=False) + f'<sup>{marker}</sup>')
                # Markers 3, 6, 14 and 15 have a one-character/space preceding span.
                if page_number == 3:
                    markdown = markdown.replace('attention heads as A.3', 'attention heads as A.<sup>3</sup>')
                if node.get('font size', 11) < 9.5:
                    markdown = re.sub(r'^(1[0-5]|[1-9])(?=[A-Za-z])', r'<sup>\1</sup> ', markdown)
                rich_locations[clean(markdown)] = {'page': page_number, 'paragraph': index}
                parts.append(markdown)
    for region in page_regions:
        if region[3] not in emitted:
            image(region)
    pages.append({'page': page_number, 'heading': f'Original PDF page {page_number}', 'paragraphs': paragraphs})
    rich_parts.extend(parts)
assert claim_location and len(pages) == 16
source_doc = {'total_pages': len(pdf), 'matched_location': None, 'pages': pages}
(root / 'bert-full.md').write_text('\n\n'.join(rich_parts) + '\n')
# Read the paper's actual bibliography, joining split entries across columns/pages.
reference_blocks = []
in_references = False
for top in layout['kids']:
    title = top.get('content', '')
    if title == 'References':
        in_references = True
        continue
    if title.startswith('Appendix for'):
        break
    if in_references:
        for node in children(top):
            reference_blocks.append((node.get('page number'), clean(node['content'])))
joined = []
pending = ''
for page, text in reference_blocks:
    if pending:
        text = pending + ' ' + text
        pending = ''
    if not re.search(r'\b(?:19|20)\d{2}[a-z]?\.', text):
        if text[:1].islower() and joined:
            joined[-1][1] += ' ' + text
        else:
            pending = text
        continue
    if not re.match(r'[A-Z]', text) and joined:
        joined[-1][1] += ' ' + text
    else:
        joined.append([page, text])
references = []
for page, raw in joined:
    match = re.match(r'(.+?)\.\s+((?:19|20)\d{2}[a-z]?)\.\s+(.+)', raw)
    if not match:
        continue
    author_text, year, rest = match.groups()
    authors = [part.strip().removeprefix('and ') for part in re.split(r',\s*|\s+and\s+', author_text) if part.strip()]
    surnames = [author.split()[-1] for author in authors]
    if author_text.startswith('Erik F Tjong Kim Sang'):
        surnames = ['Tjong Kim Sang', 'De Meulder']
    alias = surnames[0] if len(authors) == 1 else ' and '.join(surnames) if len(authors) == 2 else surnames[0] + ' et al.'
    title = re.split(r'\.\s+', rest, maxsplit=1)[0]
    references.append({'key': re.sub(r'[^a-z0-9]', '', surnames[0].lower() + year) + '-' + hashlib.sha1(title.encode()).hexdigest()[:5], 'alias': alias, 'yearLabel': year, 'year': int(year[:4]), 'title': title, 'authors': authors, 'raw': raw, 'page': page})
(root / 'bert-references.ts').write_text(
    '// Generated from the bibliography of the published BERT paper.\n'
    'export const bertReferences = ' + json.dumps(references, ensure_ascii=False, indent=2) + ';\n'
)
(root / 'bert-document.ts').write_text(
    '// Generated by scripts/prepare-bert-demo.py from the official published PDF.\n'
    'import type { SourceDocument } from "../../types/api";\n'
    'export const fullBertDocument: SourceDocument = ' + json.dumps(source_doc, ensure_ascii=False, indent=2) + ';\n'
    'export const fullBertRichLocations: Record<string, { page: number; paragraph: number }> = ' + json.dumps(rich_locations, ensure_ascii=False, indent=2) + ';\n'
    'export const fullBertClaimLocation = ' + json.dumps(claim_location) + ';\n'
)
print(json.dumps({'pages': len(pdf), 'paragraphs': sum(len(p['paragraphs']) for p in pages), 'figures': 5, 'tables': 8, 'claim': claim_location, 'sha256': hashlib.sha256(opts.pdf.read_bytes()).hexdigest()}))
