"""Streaming XLSX reader for this source format; no Excel/Office dependency."""
from __future__ import annotations
import re
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
COL = re.compile(r'^([A-Z]+)')


def _shared_strings(archive: ZipFile) -> list[str]:
    if 'xl/sharedStrings.xml' not in archive.namelist():
        return []
    strings = []
    with archive.open('xl/sharedStrings.xml') as stream:
        for _, elem in ET.iterparse(stream, events=('end',)):
            if elem.tag == NS + 'si':
                strings.append(''.join(t.text or '' for t in elem.iter(NS + 't')))
                elem.clear()
    return strings


def read_rows(path: str | Path, sheet_number: int):
    """Yield mapped column-name -> original cell text; preserve raw strings."""
    with ZipFile(path) as archive:
        strings = _shared_strings(archive)
        sheet = f'xl/worksheets/sheet{sheet_number}.xml'
        with archive.open(sheet) as stream:
            headers = None
            for _, elem in ET.iterparse(stream, events=('end',)):
                if elem.tag != NS + 'row':
                    continue
                values: dict[str, str] = {}
                for cell in elem.iter(NS + 'c'):
                    found = COL.match(cell.attrib.get('r', ''))
                    if not found:
                        continue
                    v = cell.find(NS + 'v')
                    inline = cell.find(NS + 'is')
                    value = v.text if v is not None else (
                        ''.join(t.text or '' for t in inline.iter(NS + 't'))
                        if inline is not None else None
                    )
                    if value is not None:
                        values[found.group(1)] = strings[int(value)] if cell.get('t') == 's' else str(value)
                if headers is None:
                    headers = values
                else:
                    yield {name: values.get(letter, '') for letter, name in headers.items()}
                elem.clear()
