"""Rebuild the post-hoc figure, workbook and raw-hour spot check in a fresh directory."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd


def main(output):
    root=Path(__file__).resolve().parents[2]
    tables=Path(__file__).resolve().parent/'diagnostics'
    out=Path(output)
    out.mkdir(parents=True,exist_ok=False)
    p=root/'data/raw/pvdaq_4_2017/system_4__date_2017_06_15.snappy.000.parquet'
    d=pd.read_parquet(p)
    d['measured_on']=pd.to_datetime(d.measured_on)
    d=d[d.measured_on.between('2017-06-15 12:00:00','2017-06-15 12:59:59') & d.metric_id.isin([313,315])]
    assert d.groupby('metric_id').size().eq(60).all()
    v=d.groupby('metric_id').value.mean()
    h=pd.read_parquet(root/'data/processed/final_v4/colorado/2017/primary/hourly.parquet').loc[pd.Timestamp('2017-06-15T20:00Z')]
    assert abs(v.loc[315]*.001-h.pv)<1e-12 and abs(v.loc[313]-h.irradiance)<1e-9
    record={'status':'one deterministic raw-hour normalization spot check; not a physical-cause diagnosis',
      'source':str(p.relative_to(root)),'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
      'native_hour':'2017-06-15 12:00 to 12:59','normalized_interval_end':'2017-06-15T20:00:00Z',
      'raw_ac_mean_w':v.loc[315],'raw_poa_mean_w_m2':v.loc[313],
      'normalized_ac_kw':h.pv,'samples_per_channel':60}
    (out/'raw_hour_check.json').write_text(json.dumps(record,indent=2)+'\n')
    m=pd.read_csv(tables/'monthly_source_power.csv')
    m=m[m.variant.eq('primary')]
    fig,axes=plt.subplots(1,2,figsize=(8,3),sharey=True)
    for ax,site,capacity in zip(axes,['nist','colorado'],[270.7,1]):
        for year,style in [(2016,'--'),(2017,'-')]:
            s=m[m.site.eq(site)&m.year.eq(year)]
            ax.plot(pd.to_datetime(s.month).dt.month,s.pv_mean_kw/capacity,style,marker='o',markersize=3,label=str(year))
        ax.set(title='NIST' if site=='nist' else 'Colorado',xlabel='UTC target-midpoint month',xticks=[2,4,6,8,10,12],ylim=(0,.48))
        ax.grid(axis='y',alpha=.2)
        ax.legend(frameon=False)
    axes[0].set_ylabel('Mean AC / DC capacity')
    fig.tight_layout()
    fig.savefig(out/'recorded_power_regime.pdf')
    fig.savefig(out/'recorded_power_regime.png',dpi=180)
    plt.close(fig)
    with pd.ExcelWriter(out/'Staff_Review_Diagnostics.xlsx',engine='openpyxl') as writer:
        for name in ['monthly_source_power','source_power_summary','unique_scored_target_audit','existing_summary_rows']:
            pd.read_csv(tables/f'{name}.csv').to_excel(writer,sheet_name=name[:31],index=False)
        pd.DataFrame([{'source':'Frozen PVDAQ inputs and saved evaluation; hashes in diagnostics/manifest.json',
          'doi':'10.25984/1846021','scope':'Post-hoc descriptive analysis; no exclusions or significance tests',
          'figure':'Primary monthly daylight mean AC / DC nameplate; capacities 270.7 and 1 kW'}]).to_excel(writer,sheet_name='Sources',index=False)
    (out/'build_provenance.json').write_text(json.dumps({'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'source_csv_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in tables.glob('*.csv')},
      'outputs_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}},indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    main(parser.parse_args().output)
