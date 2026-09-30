"""Verify SoccerMon and reproduce an exact bounded subset; never overwrite raw files."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path
from inspect_zip_archive import inspect_zip
from extract_zip_members import extract_selected_members, safe_destination

BUDGET = 2 * 1024**3
OFFICIAL_MD5 = 'c68f9d77ebaf042ab3e75a0714587c3c'


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n')


def hashes(path):
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with path.open('rb') as stream:
        while chunk := stream.read(8*1024**2):
            sha.update(chunk)
            md5.update(chunk)
    return {'sha256': sha.hexdigest(), 'md5': md5.hexdigest()}


def select(entries):
    by_date = defaultdict(dict)
    for entry in entries:
        if entry['extension'] != '.parquet' or entry['is_directory']:
            continue
        path = Path(entry['path'])
        day = path.parent.name
        # This inspected archive names files DATE-TeamB-PLAYER.parquet.
        player = path.stem.removeprefix(day+'-TeamB-')
        if player == path.stem or player in by_date[day]:
            raise ValueError('Unexpected or ambiguous player filename: '+str(path))
        by_date[day][player] = entry
    dates = sorted(by_date)
    if len(dates) < 3:
        raise ValueError('Fewer than three nonempty dates')
    indices = []
    for p in (0.1, 0.5, 0.9):
        target = math.floor(p*(len(dates)-1))
        indices.append(min((i for i in range(len(dates)) if i not in indices),
                           key=lambda i: (abs(i-target), i)))
    chosen_dates = [dates[i] for i in indices]
    common = set.intersection(*(set(by_date[d]) for d in chosen_dates))
    players = sorted(common, key=lambda p: (hashlib.sha256(p.encode()).hexdigest(),p))[:3]
    selected = [dict(by_date[d][p], date=d, player_filename_id=p,
                     reason='common player; SHA-256(player ID) rank; date percentile core')
                for d in chosen_dates for p in players]
    if len(selected) < 9:
        used = {e['path'] for e in selected}
        remaining = [dict(e, date=d, player_filename_id=p,
                          reason='insufficient common players; SHA-256(date, member) fallback')
                     for d in chosen_dates for p,e in by_date[d].items() if e['path'] not in used]
        remaining.sort(key=lambda e: hashlib.sha256((e['date']+'\n'+e['path']).encode()).hexdigest())
        selected.extend(remaining[:9-len(selected)])
    return {'date_count':len(dates),'date_range':[dates[0],dates[-1]],
            'date_quantile_rule':'floor(p * (n - 1)), zero-based; p=0.1,0.5,0.9',
            'quantile_tie_rule':'nearest unused index; ties choose lower index',
            'date_indices':indices,'selected_dates':chosen_dates,'common_player_count':len(common),
            'selected_common_players':players,'sessions':selected,
            'selected_size_bytes':sum(e['size_bytes'] for e in selected), 'budget_bytes':BUDGET}


def check_budget(plan, output):
    if plan['selected_size_bytes'] > BUDGET:
        raise ValueError('Proposed extraction exceeds 2 GiB; stop')
    anchor = output
    while not anchor.exists():
        anchor = anchor.parent
    existing = sum(p.stat().st_size for p in output.rglob('*') if p.is_file()) if output.exists() else 0
    if existing + plan['selected_size_bytes'] > BUDGET:
        raise ValueError('Cumulative subset exceeds 2 GiB; stop')
    free = shutil.disk_usage(anchor).free
    if free < plan['selected_size_bytes'] + 256*1024**2:
        raise OSError('Insufficient disk space; stop')
    return {'free_bytes':free,'existing_subset_bytes':existing,'required_bytes':plan['selected_size_bytes'],
            'reserve_bytes':256*1024**2}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    parser.add_argument('--output',type=Path,default=Path('data/raw/soccermon/subset'))
    parser.add_argument('--reports',type=Path,default=Path('outputs/v0b1_soccermon_inventory'))
    parser.add_argument('--extract',action='store_true')
    parser.add_argument('--expected-md5',default=OFFICIAL_MD5)
    args=parser.parse_args()
    subset_root=Path('data/raw/soccermon/subset').resolve()
    if not args.output.resolve().is_relative_to(subset_root):
        raise ValueError('Output must remain under data/raw/soccermon/subset')
    initial=args.archive.stat()
    signature=(initial.st_size,initial.st_mtime_ns)
    inventory=inspect_zip(args.archive)
    write_json(args.reports/'outer_inventory.json',inventory)
    plan=select(inventory['entries'])
    write_json(args.reports/'selection.json',plan)
    (args.reports/'selected_parquet_members.txt').write_text('\n'.join(e['path'] for e in plan['sessions'])+'\n')
    disk=check_budget(plan,subset_root)
    write_json(args.reports/'disk_before_verification.json',disk)
    print(json.dumps({k:v for k,v in plan.items() if k!='sessions'}),flush=True)
    print('Checking CRC for every archive member without disk extraction...',flush=True)
    with zipfile.ZipFile(args.archive) as archive:
        bad=archive.testzip()
    verification={'crc_checked_files':inventory['file_count'],'bad_member':bad, 'initial_size_bytes':signature[0],
                  'initial_mtime_ns':signature[1],'official_md5':args.expected_md5,
                  'official_source':'https://zenodo.org/records/10033832'}
    if bad:
        write_json(args.reports/'archive_verification.json',verification)
        raise ValueError('Corrupt member; stop: '+bad)
    print('CRC passed; computing SHA-256 and published MD5...',flush=True)
    verification.update(hashes(args.archive))
    verification['official_md5_matches']=verification['md5']==args.expected_md5
    current=args.archive.stat()
    verification['archive_unchanged']=(current.st_size,current.st_mtime_ns)==signature
    write_json(args.reports/'archive_verification.json',verification)
    if not verification['official_md5_matches'] or not verification['archive_unchanged']:
        raise ValueError('Archive verification failed; stop')
    if args.extract:
        # Validate every destination before any write; helper uses exclusive creation.
        for entry in plan['sessions']:
            if safe_destination(args.output,entry['path']).exists():
                raise FileExistsError('Selected raw destination already exists; stop')
        write_json(args.reports/'disk_before_extraction.json',check_budget(plan,subset_root))
        paths=extract_selected_members(args.archive,args.output,[e['path'] for e in plan['sessions']])
        for entry,path in zip(plan['sessions'],paths,strict=True):
            entry['extracted_path']=str(path)
            entry['extracted_size_bytes']=path.stat().st_size
            entry.update(hashes(path))
            if entry['extracted_size_bytes']!=entry['size_bytes']:
                raise ValueError('Extracted size mismatch')
        current=args.archive.stat()
        if (current.st_size,current.st_mtime_ns)!=signature:
            raise ValueError('Archive changed during extraction')
        write_json(args.reports/'extracted_manifest.json',plan)
        print('Verified and extracted exactly '+str(len(paths))+' files.',flush=True)

if __name__=='__main__':
    main()
