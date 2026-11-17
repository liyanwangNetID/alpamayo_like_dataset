#!/usr/bin/env python3
"""Generate two presentation-oriented Step 5 keyframe-selection videos.

Run from /home/lab/alpamayo_like_dataset. The script automatically chooses two
representative clips from the finalized Step 5 outputs:
  1) a dense clip with many candidate anchors and multiple selected keyframes;
  2) a clip that illustrates event deduplication when available, otherwise the
     next strongest diverse clip.

Four-camera frames use the official Step 2 timestamp synchronization gate.
"""
from __future__ import annotations
import argparse, json, math, shutil, subprocess, sys, tempfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from PIL import Image, ImageDraw, ImageFont


def find_dataset_tools_root():
    script_dir=Path(__file__).resolve().parent
    candidates=[script_dir, Path.cwd().resolve(), *Path.cwd().resolve().parents,
                Path('/home/lab/alpamayo_like_dataset/dataset_tools')]
    for p in candidates:
        if (p/'step2/clip_reader.py').is_file():
            return p
        if (p/'dataset_tools/step2/clip_reader.py').is_file():
            return p/'dataset_tools'
    raise RuntimeError(
        'dataset_tools root not found; install this script in the dataset_tools directory '
        'or run it from the repository root'
    )

DATASET_TOOLS_ROOT=find_dataset_tools_root()
REPO_ROOT=DATASET_TOOLS_ROOT.parent
if str(DATASET_TOOLS_ROOT) not in sys.path:
    sys.path.insert(0,str(DATASET_TOOLS_ROOT))
from step2.clip_reader import CAMERA_NAMES, DEFAULT_CAMERA_TOLERANCE_NS, DrivingClipReader  # noqa:E402
from step2.temporal_index import synchronize_cameras_at  # noqa:E402

W,H=1920,1080; VIDEO_W=1320; PANEL_X=1320; TIMELINE_Y=875
C={'bg':'#09111f','panel':'#111b2e','line':'#30415f','text':'#f8fafc','muted':'#afbdd1',
   'candidate':'#7890ad','selected':'#22c55e','accent':'#facc15','rejected':'#64748b','blue':'#3b82f6','orange':'#f59e0b'}
CAM_LAYOUT=(('front_wide',0,0),('front_tele',660,0),('cross_left',0,437),('cross_right',660,437))


def font(n,b=False):
    paths=[f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if b else ''}.ttf",
           f"/usr/share/fonts/truetype/liberation2/LiberationSans{'-Bold' if b else '-Regular'}.ttf"]
    for p in paths:
        if Path(p).is_file(): return ImageFont.truetype(p,n)
    return ImageFont.load_default()


def pretty(x): return str(x or 'unknown').replace('_',' ').upper()
def load_jsonl(path):
    with path.open(encoding='utf-8') as f:
        for line in f:
            if line.strip(): yield json.loads(line)

def version_key(value):
    import re
    nums=[int(x) for x in re.findall(r'\d+',str(value or ''))]
    return tuple(nums) if nums else (0,)


def inspect_jsonl_version(path):
    try:
        with path.open(encoding='utf-8') as handle:
            first=json.loads(next(line for line in handle if line.strip()))
    except (OSError,StopIteration,json.JSONDecodeError):
        return (0,), {}
    fields=(
        first.get('keyframe_format_version'),
        first.get('label_format_version'),
        first.get('feature_format_version'),
        first.get('anchor_format_version'),
        first.get('format_version'),
        first.get('selector_version'),
        first.get('generator_version'),
        first.get('profiler_version'),
    )
    strongest=max((version_key(x) for x in fields if x is not None),default=(0,))
    return strongest,first


def discover_latest_jsonl(root,patterns,description):
    candidates=[]
    for pattern in patterns:
        for path in root.glob(pattern):
            version,first=inspect_jsonl_version(path)
            candidates.append((version,path.name,path,first))
    if not candidates:
        joined=', '.join(patterns)
        raise SystemExit(f'{description} not found under {root}; patterns: {joined}')
    candidates.sort(key=lambda x:(x[0],version_key(x[1]),x[1]))
    version,name,path,first=candidates[-1]
    return path,first


def discover_annotation_paths(annotation_root):
    annotations=annotation_root/'annotations'
    if not annotations.is_dir():
        raise SystemExit(f'annotations directory not found: {annotations}')
    schema_dirs=[p for p in annotations.iterdir() if p.is_dir()]
    if not schema_dirs:
        raise SystemExit(f'No annotation version directories found under {annotations}')
    schema_dirs.sort(key=lambda p:(version_key(p.name),p.name))
    ann=schema_dirs[-1]
    inter=ann/'intermediate'
    paths={}
    paths['candidates'],_=discover_latest_jsonl(ann,['candidate_anchors*.jsonl'],'candidate anchors')
    paths['raw'],_=discover_latest_jsonl(inter,['keyframe_event_candidates_v*.jsonl'], 'raw keyframe event candidates')
    paths['dedup'],_=discover_latest_jsonl(inter,['keyframe_event_candidates_deduplicated_v*.jsonl'], 'deduplicated keyframe event candidates')
    paths['keys'],_=discover_latest_jsonl(ann,['keyframes*.jsonl'],'final keyframes')
    paths['meta'],_=discover_latest_jsonl(ann,['meta_actions_v*.jsonl'],'Meta-action labels')
    return ann,paths

def by_clip(path):
    d=defaultdict(list)
    for x in load_jsonl(path): d[x['clip_id']].append(x)
    for v in d.values(): v.sort(key=lambda x:x['anchor_ns'])
    return d

def index_anchor(path): return {x['anchor_id']:x for x in load_jsonl(path)} if path.is_file() else {}


def normalize_clip_id(value):
    value=str(value).strip()
    if not value:
        raise ValueError("empty clip identifier")
    if value.startswith("test_clip_"):
        return value
    if value.isdigit():
        return f"test_clip_{int(value):03d}"
    raise ValueError(f"invalid clip identifier: {value!r}; use 781 or test_clip_781")


def summarize_clip(clip, cands, raw, dedup, keys):
    cv=cands.get(clip,[]); kc=keys.get(clip,[])
    raw_ids={x['anchor_id'] for x in raw.get(clip,[])}
    ded_ids={x['anchor_id'] for x in dedup.get(clip,[])}
    event_types={e.get('type') for x in kc for e in x.get('events',[]) if e.get('type')}
    return {'clip':clip,'candidates':len(cv),'keyframes':len(kc),
            'dedup_removed':len(raw_ids-ded_ids),'event_types':len(event_types)}


def choose_clips(cands, raw, dedup, keys):
    rows=[summarize_clip(clip,cands,raw,dedup,keys) for clip in cands]
    eligible=[r for r in rows if r['keyframes']>=2 and r['candidates']>=5]
    if len(eligible)<2: eligible=[r for r in rows if r['keyframes']>=1 and r['candidates']>=3]
    if len(eligible)<2: raise RuntimeError('Could not find two clips with enough Step 5 decisions')
    first=max(eligible,key=lambda r:(r['keyframes'],r['candidates'],r['event_types']))
    rest=[r for r in eligible if r['clip']!=first['clip']]
    with_dedup=[r for r in rest if r['dedup_removed']>0]
    second=max(with_dedup or rest,key=lambda r:(r['dedup_removed'],r['event_types'],r['keyframes'],r['candidates']))
    return [first,second]


def sync_groups(reader,tol):
    out=[]; used={n:set() for n in CAMERA_NAMES}; rej=Counter()
    for t in reader.camera_indexes['front_wide'].timestamps_ns:
        if not reader.start_ns<=t<=reader.end_ns: rej['outside_clip']+=1; continue
        g=synchronize_cameras_at(reader.camera_indexes,t,tolerance_ns=tol,prefer_exact=True)
        if g is None: rej['sync_gate']+=1; continue
        if any(g.matches[n].index in used[n] for n in CAMERA_NAMES): rej['reused_frame']+=1; continue
        for n in CAMERA_NAMES: used[n].add(g.matches[n].index)
        out.append(g)
    return out,dict(rej)

def fit(im,w=660,h=437):
    im=im.convert('RGB'); im.thumbnail((w,h),Image.Resampling.LANCZOS)
    dst=Image.new('RGB',(w,h),'black'); dst.paste(im,((w-im.width)//2,(h-im.height)//2)); return dst

def wrap(draw,text,xy,width,font_obj,fill,spacing=6,max_lines=4):
    words=str(text).split(); lines=[]; cur=''
    for word in words:
        test=(cur+' '+word).strip()
        if draw.textbbox((0,0),test,font=font_obj)[2]<=width: cur=test
        else:
            if cur: lines.append(cur)
            cur=word
    if cur: lines.append(cur)
    y=xy[1]
    for line in lines[:max_lines]: draw.text((xy[0],y),line,font=font_obj,fill=fill); y+=font_obj.size+spacing
    return y

def nearest(items,t): return min(items,key=lambda x:abs(x['anchor_ns']-t)) if items else None


def humanize_selection_source(source):
    mapping = {
        "event": "Selected from a detected Step 5 event",
        "event_candidate": "Selected from a detected Step 5 event",
        "balanced_stable_lateral": "Selected to balance stable lateral-action coverage",
        "balanced_stable_longitudinal": "Selected to balance stable longitudinal-action coverage",
        "stable_lateral": "Selected for stable lateral-action coverage",
        "stable_longitudinal": "Selected for stable longitudinal-action coverage",
        "boundary": "Selected as a temporal boundary keyframe",
        "temporal_coverage": "Selected to improve temporal coverage",
        "quota": "Selected by the Step 5 balancing quota",
    }
    return mapping.get(source, pretty(source).title())


def humanize_selection_reason(reason, meta_action):
    lateral = pretty(meta_action.get("lateral"))
    longitudinal = pretty(meta_action.get("longitudinal"))
    if reason == "stable_lateral_turn_left":
        return "Representative stable TURN LEFT anchor retained for lateral-class balance"
    if reason == "stable_lateral_turn_right":
        return "Representative stable TURN RIGHT anchor retained for lateral-class balance"
    if reason == "stable_lateral_change_lane_left":
        return "Representative stable CHANGE LANE LEFT anchor retained for lateral-class balance"
    if reason == "stable_lateral_change_lane_right":
        return "Representative stable CHANGE LANE RIGHT anchor retained for lateral-class balance"
    if reason == "stable_lateral_keep_direction":
        return "Representative stable KEEP DIRECTION anchor retained for lateral-class balance"
    if reason.startswith("stable_lateral_"):
        return f"Representative stable {lateral} anchor retained for lateral-class balance"
    if reason.startswith("stable_longitudinal_"):
        return f"Representative stable {longitudinal} anchor retained for longitudinal-class balance"
    if reason == "contains_detected_keyframe_event":
        return "A retained Step 5 event occurs at this anchor"
    return pretty(reason).title()


def decision(anchor,raw_idx,dedup_idx,key_idx,meta_idx):
    aid=anchor['anchor_id']; key=key_idx.get(aid); raw=raw_idx.get(aid); ded=dedup_idx.get(aid); meta=meta_idx.get(aid,{})
    if key:
        selected=True; status='SELECTED KEYFRAME'; color=C['selected']
        sources=key.get('selection_sources',[])
        formal_reasons=key.get('selection_reasons',[])
        events=key.get('events',[])
        ma=key.get('meta_action',{})
        explanations=[humanize_selection_reason(r,ma) for r in formal_reasons]
        if not explanations:
            explanations=[humanize_selection_source(x) for x in sources] or ['Retained by the final Step 5 selector']
    else:
        selected=False; status='NOT SELECTED'; color=C['rejected']; sources=[]; formal_reasons=[]
        events=(ded or raw or {}).get('events',[])
        if raw and not ded:
            explanations=['A nearby duplicate event candidate was retained instead']
        elif ded:
            explanations=['The event candidate survived deduplication but was not retained by the final selector']
        else:
            explanations=['No Step 5 selection rule retained this valid anchor']
        ma=meta.get('meta_action',{})
        if not ma and meta:
            ma={'lateral':meta.get('lateral',{}).get('action') if isinstance(meta.get('lateral'),dict) else meta.get('lateral'),
                'longitudinal':meta.get('longitudinal',{}).get('action') if isinstance(meta.get('longitudinal'),dict) else meta.get('longitudinal')}
    return {'status':status,'color':color,'explanations':explanations,'sources':sources,
            'formal_reasons':formal_reasons,'events':events,'meta':ma,'selected':selected}


def draw_timeline(draw,candidates,key_ids,current_ns,start_ns,end_ns):
    x0,x1=65,W-65; y=1013
    draw.line((x0,y,x1,y),fill=C['line'],width=6)
    for a in candidates:
        x=x0+(a['anchor_ns']-start_ns)/(end_ns-start_ns or 1)*(x1-x0)
        if a['anchor_id'] in key_ids:
            draw.polygon([(x,y-14),(x+12,y),(x,y+14),(x-12,y)],fill=C['selected'])
        else: draw.line((x,y-8,x,y+8),fill=C['candidate'],width=3)
    cx=x0+(current_ns-start_ns)/(end_ns-start_ns or 1)*(x1-x0)
    draw.ellipse((cx-9,y-9,cx+9,y+9),fill='white')
    draw.text((65,922),'ALL VALID CANDIDATE ANCHORS',font=font(20,True),fill=C['text'])
    draw.line((68,960,98,960),fill=C['candidate'],width=3); draw.text((108,948),'Candidate',font=font(17),fill=C['muted'])
    draw.polygon([(260,946),(272,960),(260,974),(248,960)],fill=C['selected']); draw.text((282,948),'Selected keyframe',font=font(17),fill=C['muted'])
    draw.text((x0,1040),'CLIP START',font=font(15,True),fill=C['muted']); draw.text((x1-70,1040),'CLIP END',font=font(15,True),fill=C['muted'])


def render(g,clip,candidates,raw_idx,dedup_idx,key_idx,meta_idx,start_ns,end_ns):
    im=Image.new('RGB',(W,H),C['bg']); d=ImageDraw.Draw(im)
    for name,x,y in CAM_LAYOUT:
        rec=g.matches[name].value
        with Image.open(rec.image_path) as src: panel=fit(src)
        im.paste(panel,(x,y)); d.rectangle((x,y,x+660,y+32),fill='black'); d.text((x+11,y+5),pretty(name),font=font(17,True),fill='white')
    d.rectangle((PANEL_X,0,W,TIMELINE_Y),fill=C['panel'])
    current=nearest(candidates,g.target_ns); dec=decision(current,raw_idx,dedup_idx,key_idx,meta_idx)
    delta=abs(g.target_ns-current['anchor_ns'])/1e9; at_anchor=delta<=0.055
    d.text((PANEL_X+28,24),'STEP 5 · KEYFRAME SELECTION',font=font(22,True),fill=C['muted'])
    d.text((PANEL_X+28,62),clip,font=font(30,True),fill=C['text'])
    idx=candidates.index(current)+1
    d.text((PANEL_X+28,110),f'CANDIDATE {idx} / {len(candidates)}',font=font(18,True),fill=C['muted'])
    d.rounded_rectangle((PANEL_X+28,140,W-28,207),radius=12,fill=dec['color'])
    d.text((PANEL_X+48,158),dec['status'],font=font(28,True),fill='white')
    y=238
    d.text((PANEL_X+28,y),'META-ACTION AT THIS ANCHOR',font=font(17,True),fill=C['muted']); y+=35
    lat=dec['meta'].get('lateral','unknown'); lon=dec['meta'].get('longitudinal','unknown')
    d.rounded_rectangle((PANEL_X+28,y,W-28,y+49),radius=9,fill=C['blue']); d.text((PANEL_X+43,y+11),f'LATERAL  {pretty(lat)}',font=font(20,True),fill='white'); y+=61
    d.rounded_rectangle((PANEL_X+28,y,W-28,y+49),radius=9,fill=C['orange']); d.text((PANEL_X+43,y+11),f'LONGITUDINAL  {pretty(lon)}',font=font(20,True),fill='white'); y+=78
    d.text((PANEL_X+28,y),'WHY THIS ANCHOR WAS / WAS NOT KEPT',font=font(17,True),fill=C['muted']); y+=31
    for explanation in dec['explanations'][:2]:
        d.ellipse((PANEL_X+30,y+7,PANEL_X+40,y+17),fill=dec['color'])
        y=wrap(d,explanation,(PANEL_X+50,y),W-PANEL_X-82,font(18),C['text'],5,3)+8

    if dec['selected']:
        y=max(y,520)
        d.text((PANEL_X+28,y),'FORMAL STEP 5 AUDIT FIELDS',font=font(17,True),fill=C['muted']); y+=30
        source_text=', '.join(dec['sources']) if dec['sources'] else 'none recorded'
        reason_text=', '.join(dec['formal_reasons']) if dec['formal_reasons'] else 'none recorded'
        y=wrap(d,f"Source: {source_text}",(PANEL_X+30,y),W-PANEL_X-65,font(16),C['text'],4,2)+5
        y=wrap(d,f"Reason: {reason_text}",(PANEL_X+30,y),W-PANEL_X-65,font(16),C['text'],4,2)+8

    if dec['events']:
        y=max(y,675)
        d.text((PANEL_X+28,y),'STEP 5 EVENT EVIDENCE',font=font(17,True),fill=C['muted']); y+=30
        for ev in dec['events'][:3]:
            d.ellipse((PANEL_X+30,y+7,PANEL_X+40,y+17),fill=C['accent'])
            y=wrap(d,pretty(ev.get('type')).title(),(PANEL_X+50,y),W-PANEL_X-82,font(17),C['text'],4,2)+6
    elif dec['selected']:
        y=max(y,690)
        d.text((PANEL_X+28,y),'EVENT EVIDENCE',font=font(17,True),fill=C['muted']); y+=30
        d.text((PANEL_X+30,y),'Not event-selected; no event evidence required',font=font(16),fill=C['muted'])
    d.text((PANEL_X+28,815),f'Nearest anchor: {(g.target_ns-current["anchor_ns"])/1e9:+.2f} s',font=font(17),fill=C['muted'])
    draw_timeline(d,candidates,set(key_idx),g.target_ns,start_ns,end_ns)
    if at_anchor:
        highlight = C['selected'] if dec['selected'] else C['accent']
        label = 'KEYFRAME SELECTED · 2 s REVIEW' if dec['selected'] else 'NOT SELECTED · 1 s REVIEW'
        d.rectangle((PANEL_X+5,5,W-6,TIMELINE_Y-6),outline=highlight,width=12)
        d.rounded_rectangle((PANEL_X+215,12,W-28,54),radius=9,fill=highlight)
        d.text((PANEL_X+234,20),label,font=font(17,True),fill='#111827')
    return im


def concat_file(paths,stamps,path,fallback,selected_hold_indices=None,unselected_hold_indices=None,selected_hold_seconds=2.0,unselected_hold_seconds=1.0):
    ds=[max(.02,min(1.0,(b-a)/1e9)) for a,b in zip(stamps,stamps[1:])]; ds.append(median(ds) if ds else fallback)
    for i in (selected_hold_indices or set()):
        if 0 <= i < len(ds):
            ds[i] += selected_hold_seconds
    for i in (unselected_hold_indices or set()):
        if 0 <= i < len(ds):
            ds[i] += unselected_hold_seconds
    with path.open('w') as f:
        for p,d in zip(paths,ds):
            q=str(p).replace("'","'\\''"); f.write(f"file '{q}'\nduration {d:.9f}\n")
        q=str(paths[-1]).replace("'","'\\''"); f.write(f"file '{q}'\n")
    return sum(ds)
def encode(src,out,fps):
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(src),'-vf',f'fps={fps}','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(out)],check=True)


def main():
    p=argparse.ArgumentParser(description='Audit Step 5 keyframe-selection decisions for selected clips.')
    p.add_argument('--clip',action='append',required=True,help='Clip to audit; accepts 781 or test_clip_781. Repeat for multiple clips.')
    p.add_argument('--raw-data-root',type=Path,required=True,help='Root containing test_clip_xxx directories and camera images.')
    p.add_argument('--annotation-root',type=Path,required=True,help='Automatic annotation result root, for example /path/to/outcome_full.')
    p.add_argument('--output-root',type=Path,required=True,help='Directory in which audit videos and JSON reports are written.')
    p.add_argument('--output-fps',type=int,default=30)
    p.add_argument('--keyframe-hold-seconds',type=float,default=2.0)
    p.add_argument('--unselected-hold-seconds',type=float,default=1.0)
    p.add_argument('--tolerance-ms',type=float,default=DEFAULT_CAMERA_TOLERANCE_NS/1e6)
    args=p.parse_args()
    args.dataset_root=args.raw_data_root
    args.outcome_root=args.annotation_root
    if shutil.which('ffmpeg') is None: raise SystemExit('ffmpeg not found in PATH')
    args.raw_data_root=args.raw_data_root.expanduser().resolve()
    args.annotation_root=args.annotation_root.expanduser().resolve()
    args.output_root=args.output_root.expanduser().resolve()
    args.dataset_root=args.raw_data_root
    args.outcome_root=args.annotation_root
    if not args.raw_data_root.is_dir():
        raise SystemExit(f'Raw data root not found: {args.raw_data_root}')
    if not args.annotation_root.is_dir():
        raise SystemExit(f'Annotation result root not found: {args.annotation_root}')
    if args.output_fps <= 0 or args.keyframe_hold_seconds < 0 or args.unselected_hold_seconds < 0 or args.tolerance_ms <= 0:
        raise SystemExit('FPS and tolerance must be positive; hold durations must be non-negative')
    ann,paths=discover_annotation_paths(args.annotation_root)
    print(f'[INFO] Annotation schema directory: {ann}')
    for name,path in paths.items():
        print(f'[INFO] {name}: {path}')
    cands=by_clip(paths['candidates']); raw=by_clip(paths['raw']); dedup=by_clip(paths['dedup']); keys=by_clip(paths['keys'])
    raw_idx=index_anchor(paths['raw']); dedup_idx=index_anchor(paths['dedup']); key_idx=index_anchor(paths['keys']); meta_idx=index_anchor(paths['meta'])
    requested=[]
    for value in args.clip:
        clip=normalize_clip_id(value)
        if clip not in requested:
            requested.append(clip)
    missing=[clip for clip in requested if clip not in cands]
    if missing:
        raise SystemExit('No valid Step 3 anchors found for: '+', '.join(missing))
    missing_raw=[clip for clip in requested if not (args.raw_data_root/clip).is_dir()]
    if missing_raw:
        raise SystemExit('Raw clip directory not found for: '+', '.join(missing_raw))
    chosen=[summarize_clip(clip,cands,raw,dedup,keys) for clip in requested]
    policy='explicit user-requested audit clips'
    args.output_root.mkdir(parents=True,exist_ok=True)
    summary={'tool_version':'step5_clip_audit_v07','selection_policy':policy,'raw_data_root':str(args.raw_data_root),'annotation_root':str(args.annotation_root),'annotation_schema_directory':str(ann),'resolved_annotation_files':{k:str(v) for k,v in paths.items()},'output_root':str(args.output_root),'chosen_clips':chosen,'videos':[]}
    for number,row in enumerate(chosen,1):
        clip=row['clip']; reader=DrivingClipReader(args.dataset_root/clip); groups,rejected=sync_groups(reader,round(args.tolerance_ms*1e6))
        if not groups: raise RuntimeError(f'{clip}: no synchronized groups')
        outdir=args.output_root/(clip if len(chosen)==1 else f'{number:02d}_{clip}'); outdir.mkdir(parents=True,exist_ok=True); out=outdir/'step5_keyframe_audit_v07.mp4'
        with tempfile.TemporaryDirectory(prefix=clip+'_',dir=outdir) as td:
            td=Path(td); frames=[]
            for i,g in enumerate(groups):
                fp=td/f'f_{i:06d}.jpg'; render(g,clip,cands[clip],raw_idx,dedup_idx,key_idx,meta_idx,groups[0].target_ns,groups[-1].target_ns).save(fp,quality=94,subsampling=0); frames.append(fp)
            selected_ids={x['anchor_id'] for x in keys.get(clip,[])}
            selected_ns=[x['anchor_ns'] for x in cands[clip] if x['anchor_id'] in selected_ids]
            unselected_ns=[x['anchor_ns'] for x in cands[clip] if x['anchor_id'] not in selected_ids]
            selected_hold_indices={min(range(len(groups)),key=lambda i:abs(groups[i].target_ns-ns)) for ns in selected_ns}
            unselected_hold_indices={min(range(len(groups)),key=lambda i:abs(groups[i].target_ns-ns)) for ns in unselected_ns}
            unselected_hold_indices -= selected_hold_indices
            cf=td/'frames.ffconcat'; duration=concat_file(
                frames,[g.target_ns for g in groups],cf,1/args.output_fps,
                selected_hold_indices=selected_hold_indices,
                unselected_hold_indices=unselected_hold_indices,
                selected_hold_seconds=args.keyframe_hold_seconds,
                unselected_hold_seconds=args.unselected_hold_seconds,
            ); encode(cf,out,args.output_fps)
        report={**row,'annotation_schema_directory':str(ann),'resolved_annotation_files':{k:str(v) for k,v in paths.items()},'video':str(out),'duration_sec':duration,'accepted_sync_groups':len(groups),'sync_rejected':rejected,'selected_keyframe_hold_seconds':args.keyframe_hold_seconds,'unselected_anchor_hold_seconds':args.unselected_hold_seconds,
                'candidate_anchors':[x['anchor_id'] for x in cands[clip]],'selected_keyframes':[x['anchor_id'] for x in keys.get(clip,[])]}
        (outdir/'step5_keyframe_audit_report_v07.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
        summary['videos'].append(report); print(f"[OK] {clip}: candidates={row['candidates']} keyframes={row['keyframes']} dedup_removed={row['dedup_removed']} -> {out}")
    (args.output_root/'step5_audit_summary_v07.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    return 0
if __name__=='__main__': raise SystemExit(main())
