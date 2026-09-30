"""Full-file exploratory audit of an already selected subset; no importer or data repair.

Raw order/timestamps are preserved. Unique-time first rows are a plotting proxy,
not proof of fresh GNSS fixes. IMU magnitudes stay in documented source units.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import time
import json
import os
from pathlib import Path
import re
import sys

import numpy as np
import pyarrow.parquet as pq

os.environ.setdefault('MPLCONFIGDIR',str(Path('outputs/v0b1_soccermon_analysis/.matplotlib').resolve()))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from inspect_parquet import inspect_parquet
from prepare_soccermon_subset import hashes, write_json

GNSS=['lat','lon','speed','hacc','hdop','signal_quality','num_satellites']


def parse_time_ms(value):
    """Exact time-of-day milliseconds; no timezone, sorting, or midnight repair."""
    if not isinstance(value,str) or not re.fullmatch(r'\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?',value):
        raise ValueError('Unsupported source time: '+repr(value))
    parsed=time.fromisoformat(value)
    return ((parsed.hour*60+parsed.minute)*60+parsed.second)*1000+parsed.microsecond//1000


def interval_profile(ms):
    delta=np.diff(ms)
    positive=delta[delta>0]
    return {'interval_counts_ms':{str(int(v)):int(n) for v,n in zip(*np.unique(delta,return_counts=True))},
            'adjacent_duplicates':int(np.sum(delta==0)), 'negative_intervals':int(np.sum(delta<0)),
            'median_positive_interval_ms':float(np.median(positive)) if len(positive) else None,
            'max_positive_interval_ms':int(positive.max()) if len(positive) else None}


def numeric_profile(values,null_count=0):
    finite=values[np.isfinite(values)]
    result={'null_count':null_count,'nan_count':int(np.isnan(values).sum())-null_count,
            'infinity_count':int(np.isinf(values).sum()),'zero_count':int((values==0).sum()),
            'finite_count':len(finite)}
    if len(finite):
        q=np.quantile(finite,[0,.01,.5,.99,.999,1])
        result.update(dict(zip(['min','p01','median','p99','p999','max'],map(float,q))))
    return result


def changes(values):
    return (values[1:]!=values[:-1]) & ~(np.isnan(values[1:]) & np.isnan(values[:-1]))


def envelopes(ms,values,width_ms=10000):
    # Aggregate display only, preserving all finite min/max in each occupied bin.
    bins=(ms-ms[0])//width_ms
    x=[]; low=[]; median=[]; high=[]
    for b in np.unique(bins):
        subset=values[bins==b]
        finite=subset[np.isfinite(subset)]
        x.append((float(b)*width_ms+width_ms/2)/60000)
        if len(finite):
            low.append(float(finite.min())); median.append(float(np.median(finite))); high.append(float(finite.max()))
        else:
            low.append(np.nan); median.append(np.nan); high.append(np.nan)
    return np.array(x),np.array(low),np.array(median),np.array(high)


def inspect_session(entry):
    path=Path(entry['extracted_path'])
    if hashes(path)['sha256']!=entry['sha256']:
        raise ValueError('Raw subset checksum mismatch: '+str(path))
    pf=pq.ParquetFile(path)
    table=pf.read()
    strings=table['time'].to_pylist()
    parsed={v:parse_time_ms(v) for v in set(strings)}
    ms=np.fromiter((parsed[v] for v in strings),dtype=np.int64,count=len(strings))
    arrays={name:table[name].to_numpy(zero_copy_only=False) for name in table.column_names if name not in ('time','player_name')}
    first=np.r_[True,ms[1:]!=ms[:-1]]
    index=np.flatnonzero(first)
    bins=ms[index]
    counts=np.diff(np.r_[index,len(ms)])
    repeated=~first[1:]
    columns={name:numeric_profile(np.asarray(v,dtype=float),table[name].null_count) for name,v in arrays.items()}
    columns['time']={'null_count':table['time'].null_count,'unique_count':len(parsed),
                     'fractional_digit_counts':dict(Counter(len(s.split('.')[1]) if '.' in s else 0 for s in strings))}
    players=Counter(table['player_name'].to_pylist())
    columns['player_name']={'null_count':table['player_name'].null_count,'value_counts':dict(players)}
    duration=(int(ms[-1])-int(ms[0]))/1000
    accel=np.sqrt(sum(arrays['accl_'+a]**2 for a in 'xyz'))
    gyro=np.sqrt(sum(arrays['gyro_'+a]**2 for a in 'xyz'))
    gnss_changes=np.logical_or.reduce([changes(arrays[n].astype(float)) for n in GNSS])
    coordinate_changes=changes(arrays['lat']) | changes(arrays['lon'])
    within={n:int(np.sum(changes(v.astype(float)) & repeated)) for n,v in arrays.items()}
    lat,lon=arrays['lat'],arrays['lon']
    result={
        'path':str(path),'date':entry['date'],'player_filename_id':entry['player_filename_id'],
        'rows':len(ms),'start_time':strings[0],'end_time':strings[-1], 'duration_s':duration,
        'observed_row_density_hz':(len(ms)-1)/duration if duration>0 else None,
        'inferred_imu_nominal_hz':100,'imu_rate_status':'INFERRED from row density and within-bin axis changes; exact timing UNKNOWN',
        'row_intervals':interval_profile(ms),'time_bin_intervals':interval_profile(bins),
        'global_duplicate_timestamp_rows':len(ms)-len(parsed),
        'rows_per_contiguous_time_bin_counts':{str(int(v)):int(n) for v,n in zip(*np.unique(counts,return_counts=True))},
        'columns':columns,'changes_within_equal_timestamp':within,
        'gnss_tuple_changes_within_equal_timestamp':int(np.sum(gnss_changes & repeated)),
        'gnss_tuple_change_intervals':interval_profile(ms[np.r_[True,gnss_changes]]),
        'coordinate_change_intervals':interval_profile(ms[np.r_[True,coordinate_changes]]),
        'acceleration_magnitude_g':numeric_profile(accel),
        'gyro_magnitude_documented_deg_s':numeric_profile(gyro),
        'suspicious_counts':{
            'latitude_outside_degrees':int(np.sum(np.isfinite(lat) & (np.abs(lat)>90))),
            'longitude_outside_degrees':int(np.sum(np.isfinite(lon) & (np.abs(lon)>180))),
            'zero_coordinate_pairs':int(np.sum((lat==0)&(lon==0))),
            'negative_speed':int(np.sum(arrays['speed']<0)),
            'satellites_nonpositive':int(np.sum(arrays['num_satellites']<=0)),
            'heart_rate_zero_possible_unavailable':int(np.sum(arrays['heart_rate']==0)),
            'hacc_negative':int(np.sum(arrays['hacc']<0)),
            'hdop_nonpositive':int(np.sum(arrays['hdop']<=0))},
        'zero_coordinate_time_bins':[
            {'time':strings[int(j)], 'source_row_index':int(j),
             'speed':float(arrays['speed'][j]), 'num_satellites':int(arrays['num_satellites'][j]),
             'hacc':int(arrays['hacc'][j]),'hdop':int(arrays['hdop'][j]),
             'signal_quality':int(arrays['signal_quality'][j])}
            for j in index if lat[j]==0 and lon[j]==0],
        'unchanged_coordinate_adjacent_time_bins':int(np.sum(~(changes(lat[index]) | changes(lon[index])))),
        'schema_fields':[{'name':f.name,'type':str(f.type),'nullable':f.nullable} for f in table.schema],
        'parquet_columns':[{'name':pf.schema.column(i).name,'physical_type':pf.schema.column(i).physical_type,
                            'logical_type':str(pf.schema.column(i).logical_type),
                            'compression':pf.metadata.row_group(0).column(i).compression} for i in range(pf.metadata.num_columns)],
        'parquet_uncompressed_page_bytes':sum(pf.metadata.row_group(i).total_byte_size for i in range(pf.metadata.num_row_groups)),
        'decoded_arrow_buffer_bytes':table.nbytes,
        'player_matches_filename':set(players)=={'TeamB-'+entry['player_filename_id']}}
    return result,ms,arrays,index,accel,gyro


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=Path('outputs/v0b1_soccermon_inventory/extracted_manifest.json'))
    parser.add_argument('--output',type=Path,default=Path('outputs/v0b1_soccermon_analysis'))
    args=parser.parse_args()
    plan=json.loads(args.manifest.read_text())
    args.output.mkdir(parents=True,exist_ok=True)
    names=['gnss_trajectories','gnss_trajectories_local_view','speed_vs_time','acceleration_magnitude_vs_time','gyroscope_magnitude_vs_time','sampling_intervals','gnss_quality']
    figures={n:plt.subplots(3,3,figsize=(16,12),layout='constrained') for n in names}
    results=[]; metadata=[]
    for i,entry in enumerate(plan['sessions']):
        result,ms,a,idx,accel,gyro=inspect_session(entry)
        label=f"S{i+1}: {entry['date']} | {entry['player_filename_id'][:8]}"
        result['session_label']='S'+str(i+1)
        results.append(result)
        metadata.append(inspect_parquet(Path(entry['extracted_path'])))
        elapsed=(ms-ms[0])/60000
        lat,lon=a['lat'][idx],a['lon'][idx]
        valid=np.isfinite(lat)&np.isfinite(lon)&(np.abs(lat)<=90)&(np.abs(lon)<=180)
        origin_lat,origin_lon=float(lat[valid][0]),float(lon[valid][0])
        x=np.where(valid,6371000*np.cos(np.deg2rad(origin_lat))*np.deg2rad(lon-origin_lon),np.nan)
        y=np.where(valid,6371000*np.deg2rad(lat-origin_lat),np.nan)
        ax=figures['gnss_trajectories'][1].flat[i]
        ax.plot(x,y,lw=.35,alpha=.6)
        ax.scatter(x[0],y[0],c='green',s=15,label='first bin')
        ax.scatter(x[-1],y[-1],c='red',s=15,label='last bin')
        ax.set_aspect('equal',adjustable='datalim'); ax.set_xlabel('local east (m)');ax.set_ylabel('local north (m)')
        ax=figures['gnss_trajectories_local_view'][1].flat[i]
        zero_pair=(lat==0)&(lon==0)
        ax.plot(np.where(zero_pair,np.nan,x),np.where(zero_pair,np.nan,y),lw=.35,alpha=.65)
        ax.set_aspect('equal',adjustable='datalim');ax.set_xlabel('local east (m)');ax.set_ylabel('local north (m)')
        ax.text(.02,.02,f'{int(zero_pair.sum())} zero-pair bins omitted',transform=ax.transAxes,fontsize=8)
        ax=figures['speed_vs_time'][1].flat[i]
        ax.plot(elapsed[idx],a['speed'][idx],lw=.4)
        ax.set_xlabel('elapsed recorded time (min)');ax.set_ylabel('vendor speed (m/s)')
        for name,values,unit in [('acceleration_magnitude_vs_time',accel,'magnitude (g)'),('gyroscope_magnitude_vs_time',gyro,'magnitude (documented deg/s)')]:
            ax=figures[name][1].flat[i]
            bx,lo,med,hi=envelopes(ms,values)
            ax.fill_between(bx,lo,hi,color='#86b6d2',alpha=.6,label='10 s min–max')
            ax.plot(bx,med,lw=.7,color='#184b70',label='10 s median')
            ax.set_xlabel('elapsed recorded time (min)');ax.set_ylabel(unit)
            if i==0:ax.legend(fontsize=8)
        ax=figures['sampling_intervals'][1].flat[i]
        deltas=np.diff(ms)
        vals,counts=np.unique(deltas,return_counts=True)
        ax.bar(np.arange(len(vals)),counts)
        ax.set_xticks(np.arange(len(vals)),[str(v) for v in vals],rotation=45)
        ax.set_yscale('log');ax.set_xlabel('raw adjacent timestamp interval (ms)');ax.set_ylabel('count (log scale)')
        ax=figures['gnss_quality'][1].flat[i]
        for name in ['hacc','hdop','num_satellites']:
            bx,lo,med,hi=envelopes(ms[idx],a[name][idx])
            ax.plot(bx,med,lw=.7,label=name)
            ax.fill_between(bx,lo,hi,alpha=.15)
        ax.set_xlabel('elapsed recorded time (min)');ax.set_ylabel('source encoding / satellite count')
        if i==0:ax.legend(fontsize=8)
        for name in names:
            figures[name][1].flat[i].set_title(label,fontsize=10)
            figures[name][1].flat[i].grid(alpha=.2)
        print(label+' inspected: '+str(result['rows'])+' rows',flush=True)
    write_json(args.output/'full_profiles.json',results)
    write_json(args.output/'parquet_metadata.json',metadata)
    missing=np.array([[100*(r['columns'][n]['null_count']+r['columns'][n].get('nan_count',0)+r['columns'][n].get('infinity_count',0))/r['rows'] for n in results[0]['columns']] for r in results])
    fig,ax=plt.subplots(figsize=(15,5),layout='constrained')
    im=ax.imshow(missing,aspect='auto',vmin=0,vmax=max(1,float(missing.max())),cmap='YlOrRd')
    ax.set_xticks(range(missing.shape[1]),list(results[0]['columns']),rotation=45,ha='right')
    ax.set_yticks(range(9),[r['session_label'] for r in results])
    fig.colorbar(im,ax=ax,label='null / NaN / infinity (%)')
    ax.set_title('Missing/non-finite values — all rows; zero sentinels counted separately')
    fig.savefig(args.output/'missing_values.png',dpi=150);plt.close(fig)
    import csv
    with (args.output/'missing_values.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['session','column','rows','null','nan','infinity','zero'])
        for r in results:
            for n,p in r['columns'].items():writer.writerow([r['session_label'],n,r['rows'],p['null_count'],p.get('nan_count',0),p.get('infinity_count',0),p.get('zero_count','')])
    for name,(fig,axes) in figures.items():
        title={'gnss_trajectories':'GNSS positions: first row per contiguous timestamp bin; freshness unknown',
               'gnss_trajectories_local_view':'Local GNSS view: exact (0,0) pairs omitted for display; retained in raw figure and audit',
               'speed_vs_time':'Vendor-derived speed; first row per time bin; no ground truth',
               'acceleration_magnitude_vs_time':'Source acceleration norm; gravity semantics unknown; 10 s display envelopes',
               'gyroscope_magnitude_vs_time':'Source gyroscope norm; paper states deg/s; 10 s display envelopes',
               'sampling_intervals':'Raw stored timestamps: repeated bins are not independent IMU time measurements',
               'gnss_quality':'GNSS diagnostics: 10 s median and min–max; hacc/hdop scale unresolved'}[name]
        fig.suptitle(title,fontsize=14)
        fig.savefig(args.output/(name+'.png'),dpi=150)
        plt.close(fig)
    write_json(args.output/'analysis_summary.json',{
        'sessions':len(results),'total_rows':sum(r['rows'] for r in results),
        'schema_identical':all(r['schema_fields']==results[0]['schema_fields'] for r in results),
        'total_parquet_uncompressed_page_bytes':sum(r['parquet_uncompressed_page_bytes'] for r in results),
        'total_decoded_arrow_buffer_bytes':sum(r['decoded_arrow_buffer_bytes'] for r in results),
        'scope':'All rows of selected files; no cleaning, sorting, timestamp repair, or stream import',
        'gnss_plot_rule':'First row of each contiguous timestamp bin; within-bin conflicts counted separately',
        'imu_plot_rule':'10-second finite min/median/max envelopes only for display',
        'figures':[n+'.png' for n in names]+['missing_values.png']})

if __name__=='__main__':
    main()
