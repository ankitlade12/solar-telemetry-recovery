"""Typography-only camera-ready copies of the archived ETIC 785 result tables.

The archived exports in source/review_evidence_20261015_v2/ print negative values with a text hyphen (-0.119) while
the body text uses a true minus sign. The copies written to source/tables_cr/ differ only in that glyph and in the
Table III header notation; export() refuses to write a copy whose numbers differ from its archived source.
"""
import re
from pathlib import Path

HYPHEN_MINUS = re.compile(r'(?<![-$\w])-(?=\d)')
NUMBER = re.compile(r'-?\d+(?:\.\d+)?')
LAYOUT_LENGTH = re.compile(r'\\setlength\{[^}]*\}\{[^}]*\}')
SOURCE = Path('paper/etic2026/camera_ready_785/source')
TABLES = ('methods', 'shrinkage', 'families')  # Table I is built by export_camera_ready_table1
# Exact replacements, each of which must occur once. Table III: drop review-process wording, use the notation of
# Eq. (2), state the sign. Table IV: the true minus sign widens it by 6.3 pt, so its padding shrinks; state the sign.
EDITS = {'shrinkage': [(r'\caption{Post-review shrinkage ablation:', r'\caption{Shrinkage ablation:'),
                       (r'$a$ in $n_{eff}/(n_{eff}+a)$', r'$a$ in (\ref{eq:mixture})'),
                       (r'\scriptsize Both matched methods',
                        r'\scriptsize Positive: recovery worse than availability. Both matched methods')],
         'families': [(r'\setlength{\tabcolsep}{3pt}', r'\setlength{\tabcolsep}{2.3pt}'),
                      (r'\scriptsize Calibration variants', r'\scriptsize Positive: worse; gradual backfill. Calibration variants')]}


def typeset_minus(tex):
    return HYPHEN_MINUS.sub('$-$', tex)


def numbers(tex):
    plain = LAYOUT_LENGTH.sub('', tex).replace('$-$', '-').replace('--', ' to ')
    return [float(x) for x in NUMBER.findall(plain)]


def camera_ready(name, tex):
    for old, new in EDITS.get(name, []):
        if tex.count(old) != 1:
            raise ValueError(f'{name}: expected exactly one {old!r}')
        tex = tex.replace(old, new)
    return typeset_minus(tex)


def export(source=SOURCE):
    archived, output = source/'review_evidence_20261015_v2', source/'tables_cr'
    output.mkdir(exist_ok=True)
    for name in TABLES:
        tex = (archived/f'{name}.tex').read_text()
        copy = camera_ready(name, tex)
        if numbers(copy) != numbers(tex):
            raise ValueError(f'{name}: typography changed a reported number')
        (output/f'{name}.tex').write_text(copy)
    return output


if __name__ == '__main__':
    print(export())
