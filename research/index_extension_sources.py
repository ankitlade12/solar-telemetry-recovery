"""Read public object listings for three provisional validation-site candidates."""
import hashlib
import json
from pathlib import Path

from solar_recovery.acquire import list_objects


def main():
    out=Path('research/extension_source_availability_v1.json')
    if out.exists():
        raise FileExistsError(out)
    rows=[]
    for site in (1367,1239,10):
        for year in (2016,2017):
            prefix=f'pvdaq/parquet/pvdata/system_id={site}/year={year}/'
            objects=list_objects(prefix)
            rows.append({'system_id':site,'year':year,'prefix':prefix,
                'objects':len(objects),'bytes':sum(o['bytes'] for o in objects),'source_objects':objects})
            print(site,year,len(objects),sum(o['bytes'] for o in objects),flush=True)
    out.write_text(json.dumps({'status':'source-index availability only; no measurements or forecast performance inspected',
        'selection':'two geographically distinct catalog candidates plus a nearby Colorado system; provisional candidates, not replacements',
        'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'sources':rows},indent=2)+'\n')


if __name__=='__main__':
    main()
