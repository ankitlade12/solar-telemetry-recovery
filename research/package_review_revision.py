"""Build a local author-review bundle with verified file hashes; never upload."""
import json
from pathlib import Path
import shutil
import zipfile
import pandas as pd
from solar_recovery.pilot import digest
from research.verify_review_revision import verify


def package():
    verify()
    root=Path('runs/review_revision_20261015')
    release=Path('release/review_revision_20261015');release.mkdir(parents=True,exist_ok=False)
    selected=set()
    def add(path):
        p=Path(path)
        if not p.is_file():raise FileNotFoundError(p)
        selected.add(p)
    for name in ('README.md','ARTIFACT_GUIDE.md','DATA_AVAILABILITY.md','requirements.txt','pyproject.toml','release/THIRD_PARTY_NOTICES.md'):
        if Path(name).is_file():add(name)
    for directory in ('solar_recovery','research','tests','configs'):
        selected.update(p for p in Path(directory).glob('*.py'))
        if directory=='configs':selected.update(Path(directory).glob('*.json'))
    for pattern in ('*20261015*','new_year_protocol_2021_amendment.json'):
        selected.update(p for p in Path('research').glob(pattern) if p.is_file() and p.suffix in ('.json','.csv'))
    for parent in ('runs/final_2017_v4','runs/producing_extension_v1'):
        for name in ('manifest.json','config.json','protocol_lock.json'):add(Path(parent)/name)
        selected.update((Path(parent)/'analysis').glob('*.csv'))
    for folder in (root,Path('runs/revision_shrinkage_c10_v1')):
        selected.update(p for p in folder.rglob('*') if p.is_file() and p.suffix in ('.json','.csv','.py'))
    for folder in ('data/raw/review_revision_20261015','data/processed/review_revision_20261015'):
        selected.update(p for p in Path(folder).rglob('*') if p.is_file() and p.suffix=='.json')
    for name in ('README.md','manuscript.tex','revision_results.tex','revision_supplement.tex','reviewer_response_20261015.tex','references.bib','build.py','audit.py','render.py','requirements-paper.txt','reference_verification.json'):
        add(Path('paper')/name)
    for folder in ('paper/review_evidence_20261015_v2','paper/review_supplement_evidence_20261015','paper/vendor'):
        selected.update(p for p in Path(folder).rglob('*') if p.is_file())
    for mode in ('named','anonymous'):
        for name in ('manuscript.pdf','final_audit.json','compilation.json'):add(Path('paper/build')/mode/name)
    add('paper/build/revision_supplement/revision_supplement.pdf')
    add('paper/build/reviewer_response_20261015/reviewer_response_20261015.pdf')
    add('paper/review_revision_20261015/REPRODUCE.txt');add('paper/review_revision_20261015/visual_review.json')
    add(root/'verification/pytest.log')
    for name in ('named','anonymous','supplement','response'):
        selected.update(p for p in (Path('paper/build')/f'revision_{name}_review_v2').iterdir() if p.is_file())
    for p in sorted(selected):
        destination=release/p;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,destination)
    shutil.copyfile('paper/review_revision_20261015/REPRODUCE.txt',release/'START_HERE.txt')
    tables={'Issues':Path('research/review_revision_20261015.csv'),
            'Original contrasts':root/'analysis/contrasts.csv','Equivalence':root/'analysis/equivalence.csv',
            'Decision losses':root/'analysis/decision_losses.csv','Clock summary':root/'analysis/clock_summary.csv',
            'Transfer':root/'analysis/transfer_diagnostics.csv','All ablations':root/'experimental_analysis/contrasts.csv',
            'Support':root/'experimental_analysis/support.csv','2021 contrasts':root/'new_year/analysis/contrasts.csv',
            'State phase support':root/'verification/state_phase_support.csv',
            'Clean scores':Path('paper/review_supplement_evidence_20261015/clean_scores.csv')}
    with pd.ExcelWriter(release/'Review_Evidence.xlsx',engine='openpyxl') as writer:
        for sheet,path in tables.items():
            pd.read_csv(path).to_excel(writer,sheet_name=sheet,index=False)
            ws=writer.sheets[sheet];ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
    pd.DataFrame([dict(sheet=sheet,source=str(path),sha256=digest(path)) for sheet,path in tables.items()]).to_csv(release/'workbook_sources.csv',index=False)
    manifest=dict(status='local author-review bundle; not submitted',scope='Compact evidence and source bundle; large raw data, fitted models and forecast parquet archives remain in workspace',
                  package_code_sha256=digest(__file__),files={str(p.relative_to(release)):digest(p) for p in sorted(release.rglob('*')) if p.is_file()})
    (release/'bundle_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    archive=release.with_suffix('.zip')
    if archive.exists():raise FileExistsError(archive)
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(release.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(release))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name,expected in manifest['files'].items():
            import hashlib
            assert hashlib.sha256(z.read(name)).hexdigest()==expected,name
    archive.with_suffix('.zip.sha256').write_text(digest(archive)+'  '+archive.name+'\n')
    print(f'Packaged and hash-verified {len(manifest["files"])} files: {archive} ({archive.stat().st_size/1e6:.1f} MB)')

if __name__=='__main__':package()
