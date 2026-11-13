"""Compile the revision supplement and response without shell escape."""
from pathlib import Path
import shutil
import subprocess


def build():
    tex=shutil.which('pdflatex') or str(next((Path.home()/'Library/TinyTeX/bin').glob('*/pdflatex')))
    for name in ('revision_supplement','reviewer_response_20261015'):
        out=Path('paper/build')/name;out.mkdir(parents=True,exist_ok=True)
        for i in range(2):
            result=subprocess.run([tex,'-interaction=nonstopmode','-halt-on-error','-no-shell-escape',f'-output-directory=build/{name}',name+'.tex'],cwd='paper',capture_output=True,text=True)
            (out/f'stage_{i+1}.log').write_text(result.stdout+result.stderr)
            if result.returncode:raise RuntimeError(f'Build failed; see {out}')
        issues=[l for l in (out/(name+'.log')).read_text().splitlines() if 'Overfull' in l or 'undefined' in l]
        if issues:raise RuntimeError(issues)
        print(f'Compiled {out/(name+".pdf")}: no overflow or undefined-reference warnings')

if __name__=='__main__':build()
