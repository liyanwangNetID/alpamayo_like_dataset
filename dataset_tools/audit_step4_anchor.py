#!/usr/bin/env python3
"""Generate a Step 4 Meta-action audit video for one anchor in one clip.

Install in dataset_tools. Required inputs are explicit and portable:
  --clip, --anchor-index, --raw-data-root, --annotation-root, --output-root

Anchor indexing is 1-based after sorting candidate_anchors.jsonl by anchor_ns.
If the index is outside [1, N], the tool prints a message and creates no video.
"""
from __future__ import annotations
import argparse, ast, json, math, re, shutil, subprocess, sys, tempfile
from pathlib import Path
from statistics import median
from PIL import Image, ImageDraw, ImageFont


def find_dataset_tools_root():
    script_dir=Path(__file__).resolve().parent
    for p in [script_dir,Path.cwd().resolve(),*Path.cwd().resolve().parents,
              Path('/home/lab/alpamayo_like_dataset/dataset_tools')]:
        if (p/'step2/clip_reader.py').is_file(): return p
        if (p/'dataset_tools/step2/clip_reader.py').is_file(): return p/'dataset_tools'
    raise RuntimeError('dataset_tools root not found')

TOOLS=find_dataset_tools_root(); sys.path.insert(0,str(TOOLS))
from step2.clip_reader import CAMERA_NAMES, DEFAULT_CAMERA_TOLERANCE_NS, DrivingClipReader  # noqa:E402
from step2.temporal_index import synchronize_cameras_at  # noqa:E402

W,H=1920,1080; PANEL_X=1340; TIMELINE_Y=900
CAM_LAYOUT=(('front_wide',0,0),('front_tele',670,0),('cross_left',0,450),('cross_right',670,450))
C={'bg':'#0b1220','panel':'#111b2e','line':'#283852','text':'#f5f7fb','muted':'#aebbd0',
   'lateral':'#3b82f6','longitudinal':'#f59e0b','accent':'#facc15','speed':'#22c55e'}


def font(n,b=False):
    for p in [f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if b else ''}.ttf",
              f"/usr/share/fonts/truetype/liberation2/LiberationSans{'-Bold' if b else '-Regular'}.ttf"]:
        if Path(p).is_file(): return ImageFont.truetype(p,n)
    return ImageFont.load_default()
def pretty(x): return str(x or 'unknown').replace('_',' ').upper()
def normalize_clip_id(v):
    v=str(v).strip()
    if v.startswith('test_clip_'): return v
    if v.isdigit(): return f'test_clip_{int(v):03d}'
    raise ValueError(f'invalid clip identifier: {v!r}')
def load_jsonl(path):
    with path.open(encoding='utf-8') as f:
        for line in f:
            if line.strip(): yield json.loads(line)
def wrap(draw,text,xy,width,fnt,fill,max_lines=4):
    words=str(text).split(); lines=[]; cur=''
    for word in words:
        test=(cur+' '+word).strip()
        if draw.textbbox((0,0),test,font=fnt)[2] <= width: cur=test
        else:
            if cur: lines.append(cur)
            cur=word
    if cur: lines.append(cur)
    y=xy[1]
    for line in lines[:max_lines]: draw.text((xy[0],y),line,font=fnt,fill=fill); y+=fnt.size+5
    return y


def version_key(value):
    import re
    nums=[int(x) for x in re.findall(r'\d+',str(value or ''))]
    return tuple(nums) if nums else (0,)


def discover_latest_lateral_feature_file(intermediate_root):
    candidates=[]
    for path in intermediate_root.glob('lateral_action_features_v*.jsonl'):
        try:
            with path.open(encoding='utf-8') as handle:
                first=json.loads(next(line for line in handle if line.strip()))
            fmt=first.get('feature_format_version','0')
            profiler=first.get('profiler_version','0')
            candidates.append((version_key(fmt),version_key(profiler),path,fmt))
        except (StopIteration,ValueError,json.JSONDecodeError,OSError):
            continue
    if not candidates:
        raise SystemExit(f'No lateral_action_features_v*.jsonl found under {intermediate_root}')
    candidates.sort(key=lambda x:(x[0],x[1],x[2].name))
    return candidates[-1][2],candidates[-1][3]


def load_anchor(annotation_root,clip,index):
    ann=annotation_root/'annotations/v0.1-draft'
    cpath=ann/'candidate_anchors.jsonl'; mpath=ann/'meta_actions_v0.2.jsonl'; fpath=ann/'intermediate/meta_action_features_v0.2.jsonl'; lfpath,latest_lateral_version=discover_latest_lateral_feature_file(ann/'intermediate')
    if not cpath.is_file(): raise SystemExit(f'candidate anchor file not found: {cpath}')
    if not mpath.is_file(): raise SystemExit(f'meta action file not found: {mpath}')
    if not fpath.is_file(): raise SystemExit(f'meta action feature file not found: {fpath}')
    anchors=sorted((x for x in load_jsonl(cpath) if x.get('clip_id')==clip),key=lambda x:x['anchor_ns'])
    n=len(anchors)
    if index < 1 or index > n:
        print(f'[SKIP] {clip} has {n} valid anchors; --anchor-index must be between 1 and {n}. Requested: {index}. No video was generated.')
        return None,None,None,None,n
    anchor=anchors[index-1]
    meta=None
    for x in load_jsonl(mpath):
        if x.get('anchor_id')==anchor['anchor_id']:
            meta=x; break
    if meta is None: raise SystemExit(f"Meta-action record not found for {anchor['anchor_id']}")
    feature=None
    for x in load_jsonl(fpath):
        if x.get('anchor_id')==anchor['anchor_id']:
            feature=x; break
    if feature is None: raise SystemExit(f"Meta-action feature record not found for {anchor['anchor_id']}")
    lateral_feature=None
    for x in load_jsonl(lfpath):
        if x.get('anchor_id')==anchor['anchor_id']:
            lateral_feature=x; break
    if lateral_feature is None: raise SystemExit(f"Latest lateral feature record not found for {anchor['anchor_id']}")
    expected=meta.get('source_versions',{}).get('lateral_feature_format_version')
    actual=lateral_feature.get('feature_format_version')
    if expected and actual != expected:
        print(f'[WARN] Final label references lateral feature {expected}; audit displays latest available {actual} from {lfpath.name}.')
    lateral_feature['_audit_source_file']=str(lfpath)
    lateral_feature['_audit_latest_discovered_version']=latest_lateral_version
    lateral_feature['_label_referenced_version']=expected
    return anchor,meta,feature,lateral_feature,n


def discover_lateral_thresholds():
    """Best-effort extraction of named numeric Step 4 lateral thresholds.

    Only constants with explicit TURN/LANE/YAW/ANGLE/EXCURSION names are shown.
    The source name and file are kept in the report so the display is auditable.
    """
    found=[]
    keywords=('TURN','LANE','YAW','ANGLE','EXCURSION','HEADING','ADJACENT','DURATION','SPEED','ACCEL','DECEL','STOP')
    for path in (TOOLS/'step4').rglob('*.py'):
        try: tree=ast.parse(path.read_text(encoding='utf-8'))
        except Exception: continue
        for node in ast.walk(tree):
            if not isinstance(node,(ast.Assign,ast.AnnAssign)): continue
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            value=node.value
            if not isinstance(value,ast.Constant) or not isinstance(value.value,(int,float)): continue
            for target in targets:
                if not isinstance(target,ast.Name): continue
                name=target.id.upper()
                if any(k in name for k in keywords) and any(k in name for k in ('THRESHOLD','MIN','MAX','DELTA')):
                    found.append({'name':target.id,'value':float(value.value),'file':str(path)})
    unique=[]; seen=set()
    for item in found:
        key=(item['name'],item['value'])
        if key not in seen: seen.add(key); unique.append(item)
    return unique


def sample_ego_series(reader,groups,anchor_ns):
    series=[]
    anchor_state=reader.get_ego_state_at(anchor_ns)
    anchor_yaw=None if anchor_state is None else anchor_state.pose.yaw
    for g in groups:
        state=reader.get_ego_state_at(g.target_ns)
        if state is None: continue
        rel_yaw=None
        if anchor_yaw is not None:
            rel_yaw=math.degrees(math.atan2(math.sin(state.pose.yaw-anchor_yaw),math.cos(state.pose.yaw-anchor_yaw)))
        series.append({'target_ns':g.target_ns,'relative_sec':(g.target_ns-anchor_ns)/1e9,
                       'speed_kmh':state.speed*3.6,'relative_yaw_deg':rel_yaw,
                       'yaw_rate':state.yaw_rate})
    return series


def nearest_ego(series,target_ns):
    return min(series,key=lambda x:abs(x['target_ns']-target_ns)) if series else None

def sync_window(reader,anchor_ns,before_ns,after_ns,tol):
    out=[]; used={n:set() for n in CAMERA_NAMES}; rejected={'outside_window':0,'sync_gate':0,'reused_frame':0}
    lo,hi=anchor_ns-before_ns,anchor_ns+after_ns
    for t in reader.camera_indexes['front_wide'].timestamps_ns:
        if t<lo or t>hi: rejected['outside_window']+=1; continue
        if t<reader.start_ns or t>reader.end_ns: continue
        g=synchronize_cameras_at(reader.camera_indexes,t,tolerance_ns=tol,prefer_exact=True)
        if g is None: rejected['sync_gate']+=1; continue
        if any(g.matches[n].index in used[n] for n in CAMERA_NAMES): rejected['reused_frame']+=1; continue
        for n in CAMERA_NAMES: used[n].add(g.matches[n].index)
        out.append(g)
    return out,rejected

def fit(im,w=670,h=450):
    im=im.convert('RGB'); im.thumbnail((w,h),Image.Resampling.LANCZOS)
    dst=Image.new('RGB',(w,h),'black'); dst.paste(im,((w-im.width)//2,(h-im.height)//2)); return dst

def interpolate(a,b,u): return a+(b-a)*max(0,min(1,u))

def draw_series_chart(draw,box,title,series,key,current_ns,color,unit,zero_padding=True):
    x0,y0,x1,y1=box; draw.rounded_rectangle(box,radius=12,fill='#0b1425',outline=C['line'],width=2)
    draw.text((x0+14,y0+9),title,font=font(16,True),fill=C['text'])
    pts=[(x['relative_sec'],x.get(key)) for x in series if x.get(key) is not None]
    if not pts:
        draw.text((x0+14,y0+48),'Evidence unavailable',font=font(16),fill=C['muted']); return
    ts=[x[0] for x in pts]; vs=[x[1] for x in pts]; tmin,tmax=min(ts),max(ts)
    vmax=max(vs); vmin=min(vs)
    if zero_padding and vmin>=0: vmin=-max(1.5,(vmax+1)*.10)
    else:
        pad=max(1.0,(vmax-vmin)*.15); vmin-=pad; vmax+=pad
    if vmax<=vmin: vmax=vmin+1
    px0,py0,px1,py1=x0+40,y0+42,x1-14,y1-35
    def xy(t,v): return (px0+(t-tmin)/(tmax-tmin or 1)*(px1-px0),py1-(v-vmin)/(vmax-vmin)*(py1-py0))
    if vmin<=0<=vmax:
        zy=xy(tmin,0)[1]; draw.line((px0,zy,px1,zy),fill=C['line'],width=2)
    if tmin<=0<=tmax:
        ax=xy(0,vmin)[0]; draw.line((ax,py0,ax,py1),fill=C['accent'],width=2)
    screen=[xy(t,v) for t,v in pts]
    if len(screen)>1: draw.line(screen,fill=color,width=4)
    cur=nearest_ego(series,current_ns)
    if cur and cur.get(key) is not None:
        mx,my=xy(cur['relative_sec'],cur[key]); draw.line((mx,py0,mx,py1),fill='white',width=2); draw.ellipse((mx-7,my-7,mx+7,my+7),fill=C['accent'],outline='white',width=2)
        draw.text((x0+14,y1-27),f"CURRENT {cur[key]:+.1f} {unit}" if key!='speed_kmh' else f"CURRENT {cur[key]:.1f} {unit}",font=font(15,True),fill=C['text'])


def relevant_thresholds(thresholds,action):
    action=action.lower()
    if 'turn' in action:
        preferred=[x for x in thresholds if 'TURN' in x['name'].upper() and any(k in x['name'].upper() for k in ('YAW','ANGLE','EXCURSION'))]
    elif 'lane' in action:
        preferred=[x for x in thresholds if 'LANE' in x['name'].upper() or 'ADJACENT' in x['name'].upper()]
    else:
        preferred=[x for x in thresholds if any(k in x['name'].upper() for k in ('TURN','YAW','ANGLE','EXCURSION'))]
    return preferred[:3]


def relevant_longitudinal_thresholds(thresholds,action):
    action=action.lower()
    names=[]
    if action == 'accelerate':
        names=[x for x in thresholds if any(k in x['name'].upper() for k in ('ACCEL','SPEED_DELTA')) and 'DECEL' not in x['name'].upper()]
    elif action == 'decelerate':
        names=[x for x in thresholds if any(k in x['name'].upper() for k in ('DECEL','SPEED_DELTA'))]
    elif action == 'stop':
        names=[x for x in thresholds if any(k in x['name'].upper() for k in ('STOP','ZERO','SPEED'))]
    else:
        names=[x for x in thresholds if any(k in x['name'].upper() for k in ('SPEED_DELTA','ACCEL','DECEL'))]
    return names[:4]


def supporting_evidence(meta,feature,lateral_feature,ego_series):
    lat=meta.get('lateral',{}).get('action','unknown')
    lon=meta.get('longitudinal',{}).get('action','unknown')
    items=[]
    lf=lateral_feature.get('lateral',{})
    relative=lf.get('natural_corridor',{}).get('relative_heading',{})
    map_change=lf.get('map_corridor_heading_change_rad')
    ego_change=lf.get('ego_total_yaw_change_rad')
    max_relative=relative.get('maximum_absolute_relative_heading_rad')
    if ego_change is not None:
        items.append(f'Global ego yaw over horizon: {math.degrees(ego_change):+.1f} deg')
    if map_change is not None:
        items.append(f'Map corridor heading change: {math.degrees(map_change):+.1f} deg')
    if max_relative is not None:
        items.append(f'Max ego-to-corridor heading error: {math.degrees(max_relative):.1f} deg')
    metrics=feature.get('longitudinal',{})
    delta=metrics.get('speed_delta_mps')
    if delta is not None: items.append(f'Speed change: {delta*3.6:+.1f} km/h')
    return items[:4]


def draw_threshold_lines(draw,x,y,title,items,width,max_lines=4):
    draw.text((x,y),title,font=font(13,True),fill=C['muted']); y+=19
    if not items:
        draw.text((x,y),'Not discoverable as a named Step 4 constant',font=font(12),fill=C['accent'])
        return y+17
    for item in items[:max_lines]:
        text=f"{item['name']} = {item['value']:g}"
        y=wrap(draw,text,(x,y),width,font(12),C['accent'],2)+2
    return y


def draw_lateral_evidence(draw,box,meta,feature,lateral_feature,series,current_ns):
    x0,y0,x1,y1=box
    draw_series_chart(draw,(x0,y0,x1,y1),'GLOBAL EGO HEADING CHANGE · AUDIT SIGNAL',series,'relative_yaw_deg',current_ns,C['lateral'],'deg',False)
    metrics=meta.get('lateral',{}).get('metrics',{})
    current=nearest_ego(series,current_ns)
    yaw_now=None if current is None else current.get('relative_yaw_deg')


def render(g,clip,index,total,anchor,meta,feature,lateral_feature,ego_series,start_ns,end_ns,before_sec,after_sec):
    im=Image.new('RGB',(W,H),C['bg']); d=ImageDraw.Draw(im)
    for name,x,y in CAM_LAYOUT:
        rec=g.matches[name].value
        with Image.open(rec.image_path) as src: pane=fit(src)
        im.paste(pane,(x,y)); d.rectangle((x,y,x+670,y+34),fill='black'); d.text((x+12,y+5),pretty(name),font=font(18,True),fill='white')
    d.rectangle((PANEL_X,0,W,TIMELINE_Y),fill=C['panel'])
    lat=meta.get('lateral',{}); lon=meta.get('longitudinal',{}); rel=(g.target_ns-anchor['anchor_ns'])/1e9
    d.text((PANEL_X+28,24),'STEP 4 · META-ACTION AUDIT',font=font(22,True),fill=C['muted'])
    d.text((PANEL_X+28,62),clip,font=font(29,True),fill=C['text']); d.text((PANEL_X+28,103),f'ANCHOR {index} / {total}',font=font(19,True),fill=C['muted'])
    y=142
    for label,obj,color in [('LATERAL ACTION',lat,C['lateral']),('LONGITUDINAL ACTION',lon,C['longitudinal'])]:
        d.text((PANEL_X+28,y),label,font=font(15,True),fill=C['muted']); y+=22
        d.rounded_rectangle((PANEL_X+28,y,W-28,y+47),radius=9,fill=color); d.text((PANEL_X+47,y+11),pretty(obj.get('action')),font=font(21,True),fill='white'); y+=58
    d.text((PANEL_X+28,338),'SUPPORTING EVIDENCE',font=font(16,True),fill=C['muted'])
    ey=364
    for item in supporting_evidence(meta,feature,lateral_feature,ego_series)[:3]:
        d.ellipse((PANEL_X+30,ey+7,PANEL_X+42,ey+19),fill=C['accent'])
        d.text((PANEL_X+54,ey),item,font=font(17),fill=C['text']); ey+=26
    draw_lateral_evidence(d,(PANEL_X+24,446,W-24,655),meta,feature,lateral_feature,ego_series,g.target_ns)
    draw_series_chart(d,(PANEL_X+24,670,W-24,865),'LONGITUDINAL SPEED EVIDENCE',ego_series,'speed_kmh',g.target_ns,C['speed'],'km/h',True)
    d.rectangle((0,TIMELINE_Y,W,H),fill='#08101d'); d.text((30,920),f'TEMPORAL CONTEXT   t = {rel:+.2f} s',font=font(23,True),fill=C['text'])
    x0,x1=85,W-85; ty=1018; d.line((x0,ty,x1,ty),fill=C['line'],width=7)
    pos=x0+(g.target_ns-start_ns)/(end_ns-start_ns or 1)*(x1-x0); apos=x0+(anchor['anchor_ns']-start_ns)/(end_ns-start_ns or 1)*(x1-x0); apos=max(x0,min(x1,apos))
    d.line((apos,970,apos,1052),fill=C['accent'],width=5); d.text((apos-35,945),'ANCHOR',font=font(16,True),fill=C['accent']); d.ellipse((pos-9,ty-9,pos+9,ty+9),fill='white')
    d.text((x0,1045),f'-{before_sec:.1f} s',font=font(15,True),fill=C['muted']); d.text((x1-54,1045),f'+{after_sec:.1f} s',font=font(15,True),fill=C['muted'])
    if abs(rel)<=.055:
        d.rectangle((PANEL_X+5,5,W-6,TIMELINE_Y-6),outline=C['accent'],width=10); d.rounded_rectangle((PANEL_X+275,12,W-28,53),radius=9,fill=C['accent']); d.text((PANEL_X+294,20),'META-ACTION ANCHOR',font=font(18,True),fill='#111827')
    return im

def ffconcat(paths,stamps,path,fallback,anchor_index,hold):
    ds=[max(.02,min(1,(b-a)/1e9)) for a,b in zip(stamps,stamps[1:])]; ds.append(median(ds) if ds else fallback); ds[anchor_index]+=hold
    with path.open('w') as f:
        for p,d in zip(paths,ds):
            q=str(p).replace("'","'\\''"); f.write(f"file '{q}'\nduration {d:.9f}\n")
        q=str(paths[-1]).replace("'","'\\''"); f.write(f"file '{q}'\n")
    return sum(ds)

def encode(src,out,fps):
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(src),'-vf',f'fps={fps}','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(out)],check=True)


def main():
    p=argparse.ArgumentParser(description='Generate a Step 4 audit video for one 1-based anchor index.')
    p.add_argument('--clip',required=True,help='781 or test_clip_781')
    p.add_argument('--anchor-index',type=int,required=True,help='1-based index in time-sorted valid anchors')
    p.add_argument('--raw-data-root',type=Path,required=True)
    p.add_argument('--annotation-root',type=Path,required=True)
    p.add_argument('--output-root',type=Path,required=True)
    p.add_argument('--before-seconds',type=float,default=2.0); p.add_argument('--after-seconds',type=float,default=3.0)
    p.add_argument('--anchor-hold-seconds',type=float,default=2.0); p.add_argument('--output-fps',type=int,default=30)
    p.add_argument('--tolerance-ms',type=float,default=DEFAULT_CAMERA_TOLERANCE_NS/1e6); args=p.parse_args()
    if shutil.which('ffmpeg') is None: raise SystemExit('ffmpeg not found in PATH')
    clip=normalize_clip_id(args.clip); raw=args.raw_data_root.expanduser().resolve(); ann=args.annotation_root.expanduser().resolve(); outroot=args.output_root.expanduser().resolve()
    if not raw.is_dir(): raise SystemExit(f'Raw data root not found: {raw}')
    if not ann.is_dir(): raise SystemExit(f'Annotation result root not found: {ann}')
    if not (raw/clip).is_dir(): raise SystemExit(f'Raw clip directory not found: {raw/clip}')
    if args.before_seconds<0 or args.after_seconds<=0 or args.anchor_hold_seconds<0 or args.output_fps<=0 or args.tolerance_ms<=0: raise SystemExit('Invalid timing/FPS/tolerance arguments')
    anchor,meta,feature,lateral_feature,total=load_anchor(ann,clip,args.anchor_index)
    if anchor is None: return 0
    reader=DrivingClipReader(raw/clip); groups,rejected=sync_window(reader,anchor['anchor_ns'],round(args.before_seconds*1e9),round(args.after_seconds*1e9),round(args.tolerance_ms*1e6))
    if not groups: raise SystemExit('No synchronized camera groups in the requested window; no video generated')
    ego_series=sample_ego_series(reader,groups,anchor['anchor_ns'])
    outdir=outroot/clip/f"anchor_{args.anchor_index:03d}"; outdir.mkdir(parents=True,exist_ok=True); video=outdir/'step4_meta_action_audit_v07.mp4'
    with tempfile.TemporaryDirectory(prefix='render_',dir=outdir) as td:
        td=Path(td); frames=[]
        for i,g in enumerate(groups):
            fp=td/f'f_{i:06d}.jpg'; render(g,clip,args.anchor_index,total,anchor,meta,feature,lateral_feature,ego_series,groups[0].target_ns,groups[-1].target_ns,args.before_seconds,args.after_seconds).save(fp,quality=94,subsampling=0); frames.append(fp)
        nearest=min(range(len(groups)),key=lambda i:abs(groups[i].target_ns-anchor['anchor_ns'])); cf=td/'frames.ffconcat'; duration=ffconcat(frames,[g.target_ns for g in groups],cf,1/args.output_fps,nearest,args.anchor_hold_seconds); encode(cf,video,args.output_fps)
    report={'tool_version':'step4_anchor_audit_v07','clip_id':clip,'anchor_index':args.anchor_index,'anchor_count':total,'anchor_id':anchor['anchor_id'],'anchor_ns':anchor['anchor_ns'],'raw_data_root':str(raw),'annotation_root':str(ann),'output_root':str(outroot),'window_seconds':{'before':args.before_seconds,'after':args.after_seconds},'anchor_hold_seconds':args.anchor_hold_seconds,'meta_action':meta,'meta_action_features':feature,'lateral_action_features_latest':lateral_feature,'ego_series':ego_series,'synchronization':{'accepted_groups':len(groups),'rejected':rejected,'tolerance_ns':round(args.tolerance_ms*1e6)},'duration_sec':duration,'video':str(video)}
    (outdir/'step4_meta_action_audit_report_v07.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(f"[OK] {clip} anchor {args.anchor_index}/{total}: {pretty(meta['lateral']['action'])} + {pretty(meta['longitudinal']['action'])}")
    print(f'[OK] Video: {video}')
    return 0
if __name__=='__main__': raise SystemExit(main())
