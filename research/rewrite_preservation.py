"""Check that an author rewrite of ETIC 785 keeps every fact the verified LaTeX states.

The authors may change every sentence. They may not lose or alter a number, a citation, a cross-reference, a
label, an included table or figure, or a displayed equation. The report lists what is missing from the rewrite and
what it adds, for a human to judge; it does not judge wording.

    python3 research/rewrite_preservation.py VERIFIED_SOURCE_DIR REWRITTEN_SOURCE_DIR
"""
import re
import sys
from collections import Counter
from pathlib import Path

PROSE_FILES = ('manuscript.tex', 'camera_ready_statistics.tex', 'revision_results.tex')
ARGUMENT = r'\{([^}]*)\}'
KEYED = {'citations': r'\\cite' + ARGUMENT, 'references': r'\\ref' + ARGUMENT, 'labels': r'\\label' + ARGUMENT,
         'inputs': r'\\input' + ARGUMENT, 'graphics': r'\\includegraphics(?:\[[^\]]*\])?' + ARGUMENT}
NOT_PROSE = re.compile(r'\\(?:cite|ref|label|input|includegraphics|url|setlength)(?:\[[^\]]*\])?(?:\{[^}]*\})+')
EQUATION = re.compile(r'\\begin\{equation\}(.*?)\\end\{equation\}', re.S)
COMMAND = re.compile(r'\\[A-Za-z]+')
NUMBER = re.compile(r'(?<![\w.])[-+]?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)')
WORDS = dict(zip('two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen '
                 'seventeen eighteen nineteen twenty'.split(), range(2, 21)))
WORD = re.compile(r'\b(' + '|'.join(WORDS) + r')\b', re.I)


def canonical(token):
    value = float(token.replace(',', ''))
    text = repr(value + 0.0)
    return text[:-2] if text.endswith('.0') else text


def numbers(tex):
    plain = NOT_PROSE.sub(' ', tex).replace('$-$', '-').replace('\\textminus', '-').replace('--', ' to ')
    plain = plain.replace('{,}', ',')
    plain = WORD.sub(lambda m: str(WORDS[m.group(1).lower()]), COMMAND.sub(' ', plain))
    return Counter(canonical(t) for t in NUMBER.findall(plain) if any(c.isdigit() for c in t))


def facts(tex):
    found = {'numbers': numbers(tex),
             'equations': Counter(' '.join(body.split()) for body in EQUATION.findall(tex))}
    for kind, pattern in KEYED.items():
        found[kind] = Counter({key.strip(): 1 for group in re.findall(pattern, tex) for key in group.split(',')})
    return found


def compare(verified, rewrite):
    old, new = facts(verified), facts(rewrite)
    report = {}
    for kind in old:
        missing, added = old[kind] - new[kind], new[kind] - old[kind]
        if missing or added:
            report[kind] = {'missing': sorted(missing.elements()), 'added': sorted(added.elements())}
    return report


def read_prose(source):
    return '\n'.join((Path(source)/name).read_text() for name in PROSE_FILES)


def main(verified_dir, rewrite_dir):
    report = compare(read_prose(verified_dir), read_prose(rewrite_dir))
    for kind, change in report.items():
        print(f'{kind}:\n  missing from rewrite: {change["missing"]}\n  added in rewrite:    {change["added"]}')
    print('No fact lost.' if not any(c['missing'] for c in report.values()) else 'Facts missing: review before use.')
    return 1 if any(c['missing'] for c in report.values()) else 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:3]))
