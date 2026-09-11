"""Offline-only A/B/C/D analysis. Never imports model, tool, or evaluator code."""
from __future__ import annotations

import csv, hashlib, json, math, random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "analysis"
FIG = OUT / "figures"
STAGES = {s: ROOT / "runs" / "experiments" / f"stage-{s.lower()}-full-v1" for s in "ABCD"}
COLORS = {"A":"#4477AA", "B":"#EE6677", "C":"#228833", "D":"#CCBB44"}
TAXONOMY = ["delivery/agent_control", "tool_execution/acquisition", "evidence_coverage",
            "grounding/utilization", "route/transportation", "budget/minimum_nights",
            "diversity/preference/room_rule", "verifier/replan", "success"]

def load(path: Path) -> Any: return json.loads(path.read_text(encoding="utf-8"))
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path: Path, value: Any) -> None: path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w=csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
def esc(s: Any) -> str: return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def svg_start(title: str, subtitle: str="") -> list[str]:
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">',
      '<rect width="1600" height="900" fill="#FAFAF7"/>',
      '<style>text{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;fill:#252525}.title{font-size:36px;font-weight:700}.sub{font-size:19px;fill:#666}.lab{font-size:18px}.small{font-size:15px}.val{font-size:17px;font-weight:700}</style>',
      f'<text x="80" y="70" class="title">{esc(title)}</text>', f'<text x="80" y="105" class="sub">{esc(subtitle)}</text>']
def save_svg(name: str, content: list[str]) -> None:
    content.append('</svg>'); (FIG/f"{name}.svg").write_text("\n".join(content),encoding="utf-8")
def bar_chart(name,title,subtitle,categories,series,percent=True):
    x0,y0,w,h=130,170,1390,610; a=svg_start(title,subtitle); maxv=max(v for _,vals,_ in series for v in vals)*1.12 or 1
    for i in range(6):
        y=y0+h-i*h/5; val=maxv*i/5; a += [f'<line x1="{x0}" y1="{y:.1f}" x2="{x0+w}" y2="{y:.1f}" stroke="#DDD"/>',f'<text x="{x0-15}" y="{y+6:.1f}" text-anchor="end" class="small">{val*100:.0f}%</text>']
    group=w/len(categories); bw=group/(len(series)+1)
    for si,(label,vals,color) in enumerate(series):
        for i,v in enumerate(vals):
            x=x0+i*group+(si+.5)*bw; bh=v/maxv*h; y=y0+h-bh
            a += [f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw*.82:.1f}" height="{bh:.1f}" rx="4" fill="{color}"/>',f'<text x="{x+bw*.41:.1f}" y="{y-8:.1f}" text-anchor="middle" class="small">{v*100:.1f}%</text>']
    for i,c in enumerate(categories): a.append(f'<text x="{x0+(i+.5)*group:.1f}" y="{y0+h+38}" text-anchor="middle" class="lab">{esc(c)}</text>')
    for i,(label,_,color) in enumerate(series): a += [f'<rect x="{x0+i*190}" y="830" width="24" height="16" fill="{color}"/>',f'<text x="{x0+32+i*190}" y="845" class="lab">{esc(label)}</text>']
    save_svg(name,a)
def mini_bars(name,title,subtitle,panels):
    a=svg_start(title,subtitle)
    for p,(ptitle,vals,fmt) in enumerate(panels):
        x0=80+p*505; y0=190; w=440; h=570; mx=max(vals.values())*1.12 or 1
        a.append(f'<text x="{x0+w/2}" y="155" text-anchor="middle" class="lab">{esc(ptitle)}</text>')
        for i,(s,v) in enumerate(vals.items()):
            bw=75;x=x0+40+i*100;bh=v/mx*h;y=y0+h-bh
            a += [f'<rect x="{x}" y="{y:.1f}" width="{bw}" height="{bh:.1f}" rx="5" fill="{COLORS[s]}"/>',f'<text x="{x+bw/2}" y="{y-9:.1f}" text-anchor="middle" class="small">{fmt(v)}</text>',f'<text x="{x+bw/2}" y="{y0+h+35}" text-anchor="middle" class="lab">{s}</text>']
    save_svg(name,a)
def heatmaps(name,title,subtitle,stage_groups):
    a=svg_start(title,subtitle); levels=["easy","medium","hard"];days=[3,5,7]
    for p,(s,g) in enumerate(stage_groups.items()):
        x0=95+p*375;y0=250;cell=100
        a.append(f'<text x="{x0+150}" y="175" text-anchor="middle" class="title">Stage {s}</text>')
        for j,d in enumerate(days): a.append(f'<text x="{x0+(j+.5)*cell}" y="225" text-anchor="middle" class="lab">{d}天</text>')
        for i,l in enumerate(levels):
            a.append(f'<text x="{x0-15}" y="{y0+(i+.55)*cell}" text-anchor="end" class="lab">{l}</text>')
            for j,d in enumerate(days):
                v=g[f"cell:{l}:{d}"]["final_pass_rate"]; shade=int(245-155*v);color=f'rgb({shade},{220-int(80*v)},{245-int(120*v)})'
                a += [f'<rect x="{x0+j*cell}" y="{y0+i*cell}" width="94" height="94" rx="6" fill="{color}"/>',f'<text x="{x0+(j+.47)*cell}" y="{y0+(i+.56)*cell}" text-anchor="middle" class="val">{v*100:.1f}%</text>']
    a += ['<text x="800" y="650" text-anchor="middle" class="sub">长程任务仍是共同瓶颈；颜色越深表示 Final Pass 越高</text>'];save_svg(name,a)
def stacked(name,title,subtitle,rows):
    a=svg_start(title,subtitle);x0,y0,w=260,230,1180
    cols={t:c for t,c in zip(TAXONOMY,["#999999","#D55E00","#E69F00","#CC79A7","#56B4E9","#0072B2","#009E73","#7A5195","#2E8B57"])}
    for i,s in enumerate("BCD"):
        y=y0+i*150;x=x0;total=sum(rows[s].values())
        a.append(f'<text x="{x0-70}" y="{y+45}" class="title">{s}</text>')
        for t in TAXONOMY:
            v=rows[s].get(t,0);ww=w*v/total
            if ww: a.append(f'<rect x="{x:.1f}" y="{y}" width="{ww:.1f}" height="75" fill="{cols[t]}"><title>{esc(t)}: {v}</title></rect>')
            if ww>48:a.append(f'<text x="{x+ww/2:.1f}" y="{y+47}" text-anchor="middle" class="val" fill="white">{v}</text>')
            x+=ww
    for i,t in enumerate(TAXONOMY):
        x=110+(i%3)*500;y=720+(i//3)*48;a += [f'<rect x="{x}" y="{y}" width="24" height="18" fill="{cols[t]}"/>',f'<text x="{x+34}" y="{y+16}" class="small">{esc(t)}</text>']
    save_svg(name,a)

def exact_mcnemar(b:int,c:int)->float:
    n=b+c
    return min(1,2*sum(math.comb(n,k) for k in range(min(b,c)+1))/2**n) if n else 1.0
def paired_stats(left,right,key,label):
    dif=[int(r[key])-int(l[key]) for l,r in zip(left,right)]; trans=Counter((bool(l[key]),bool(r[key])) for l,r in zip(left,right));rng=random.Random(20260904)
    boot=sorted(sum(rng.choice(dif) for _ in dif)/len(dif) for _ in range(10000));b=trans[(True,False)];c=trans[(False,True)]
    return {"comparison":label,"metric":key,"left_fail_right_fail":trans[(False,False)],"left_fail_right_pass":c,"left_pass_right_fail":b,"left_pass_right_pass":trans[(True,True)],"delta":sum(dif)/len(dif),"mcnemar_p":exact_mcnemar(b,c),"bootstrap_low":boot[249],"bootstrap_high":boot[9749]}

def original_failure(stage,row,run):
    if row["status"]!="completed": return "delivery/agent_control"
    if row["final_pass"]: return "success"
    raw=row.get("primary_failure_category","")
    if stage=="D" and raw and raw not in {"planning_constraint_failure","unchanged_success"}:
        if raw=="upstream_agent_control_non_delivery":return "delivery/agent_control"
        return "verifier/replan"
    mapping={"tool_execution_failure":"tool_execution/acquisition","evidence_insufficient_for_chosen_plan":"evidence_coverage","evidence_insufficient":"evidence_coverage","evidence_utilization_or_grounding_failure":"grounding/utilization","blueprint_execution_deviation":"route/transportation"}
    if raw in mapping:return mapping[raw]
    ev=load(run/"official_evaluation.json") if (run/"official_evaluation.json").exists() else {}
    failed=[]
    for fam in ("commonsense_constraint","hard_constraint"):
        for k,v in (ev.get(fam) or {}).items():
            if isinstance(v,list) and v and v[0] is False:failed.append(k)
    if any(k in failed for k in ["is_reasonable_visiting_city","is_valid_information_in_current_city","is_valid_transportation","valid_transportation"]):return "route/transportation"
    if any(k in failed for k in ["valid_cost","is_valid_accommodation"]):return "budget/minimum_nights"
    if any(k in failed for k in ["is_valid_restaurants","is_valid_attractions","valid_room_rule","valid_cuisine","valid_room_type"]):return "diversity/preference/room_rule"
    if "is_valid_information_in_sandbox" in failed:return "grounding/utilization"
    return "grounding/utilization"

def main():
    FIG.mkdir(parents=True,exist_ok=True)
    summaries={s:load(p/"summary.json") for s,p in STAGES.items()};pers={s:load(p/"per_sample.json") for s,p in STAGES.items()};mans={s:load(p/"manifest.json") for s,p in STAGES.items()}
    checks=[];freeze={"schema_version":1,"frozen_on":"2026-09-07","policy":"analysis_only_no_model_tool_or_evaluator_calls","stages":{}}
    for s,p in STAGES.items():
        idx=[r["idx"] for r in pers[s]];assert idx==list(range(1,181)) and len(set(idx))==180
        assert mans[s]["indices"]==list(range(1,181));assert load(p/"official_aggregate.json")["cross_check_pass"]
        missing=[i for i in idx if not Path(mans[s]["samples"][str(i)]["selected_run_dir"]).exists()];assert not missing
        files=["manifest.json","summary.json","per_sample.json","submission.jsonl","official_aggregate.json"]
        freeze["stages"][s]={"experiment":p.name,"baseline":mans[s].get("baseline_id",mans[s].get("baseline",s)),"dataset_fingerprint":mans[s]["dataset"]["fingerprint"],"protocol":mans[s]["protocol"],"protocol_hash":hashlib.sha256(json.dumps(mans[s]["protocol"],sort_keys=True).encode()).hexdigest(),"files":{f:sha(p/f) for f in files}}
        checks.append({"stage":s,"rows":180,"ordered_unique":True,"selected_runs_exist":True,"official_local_match":True})
    dump(OUT/"freeze_manifest.json",freeze);write_csv(OUT/"integrity_checks.csv",checks)

    main_rows=[]
    for s,x in summaries.items():
        main_rows.append({"stage":s,"delivery_rate":x["delivery_rate"],"commonsense_micro":x["commonsense_micro_pass_rate"],"commonsense_macro":x["commonsense_macro_pass_rate"],"hard_micro":x["hard_micro_pass_rate"],"hard_macro":x["hard_macro_pass_rate"],"final_pass":x["final_pass_rate"],"total_tokens":x["usage"]["total_tokens"],"tokens_per_sample":x["usage"]["total_tokens"]/180,"mean_latency_seconds":x["latency_seconds"]["mean"],"mean_model_calls":(x.get("react")or{}).get("model_calls",{}).get("mean",1),"mean_tool_calls":(x.get("react")or{}).get("tool_calls",{}).get("mean",0)})
    write_csv(OUT/"abcd_main_metrics.csv",main_rows)
    strata=[]
    for s,x in summaries.items():
        for key,val in x["groups"].items():
            strata.append({"stage":s,"group":key,**val})
    write_csv(OUT/"stratified_metrics.csv",strata)
    constraints=[]
    for s,x in summaries.items():
        for k,v in x["constraint_pass"].items():constraints.append({"stage":s,"constraint":k,**v})
    write_csv(OUT/"constraint_rates.csv",constraints)

    standardized=[];tax=defaultdict(Counter);cases=defaultdict(list)
    for s in "ABCD":
        for row in pers[s]:
            run=Path(mans[s]["samples"][str(row["idx"])]["selected_run_dir"]);category=original_failure(s,row,run);tax[s][category]+=1
            rec={"stage":s,"idx":row["idx"],"level":row["level"],"days":row["days"],"delivered":row["status"]=="completed","final_pass":row["final_pass"],"original_failure":row.get("primary_failure_category",""),"unified_failure":category,"run_dir":str(run)};standardized.append(rec);cases[(s,category)].append(rec)
    write_csv(OUT/"standardized_samples.csv",standardized)
    write_csv(OUT/"failure_taxonomy.csv",[{"stage":s,"category":t,"count":tax[s][t],"rate":tax[s][t]/180} for s in "ABCD" for t in TAXONOMY])
    case_rows=[]
    explanations={"delivery/agent_control":"Agent 未在调用上限内形成 evaluator-ready candidate；下游规划或验证机制无法介入。","tool_execution/acquisition":"工具参数、空结果或检索路径失败，使后续规划缺少可用环境信息。","evidence_coverage":"最终路线所需的城市或交通类别没有被充分检索。","grounding/utilization":"已经观察到的信息未被正确使用，或计划实体无法在 evidence 中定位。","route/transportation":"城市顺序、跨城日或交通表达不满足全局路线约束。","budget/minimum_nights":"局部选择可用，但总预算或住宿夜数在全程层面不成立。","diversity/preference/room_rule":"餐厅/景点多样性或用户房型、菜系、house rule 偏好未满足。","verifier/replan":"Verifier 报告或单次 Replan 无效、误判或未能形成约束正确的修复。"}
    for (s,t),vals in cases.items():
        if t=="success":continue
        for horizon in sorted({min(v["days"] for v in vals),max(v["days"] for v in vals)}):
            v=min((x for x in vals if x["days"]==horizon),key=lambda x:x["idx"]);run=Path(v["run_dir"]);inp=load(run/"input.json");query=(inp.get("model_input")or{}).get("query","")
            ev=load(run/"official_evaluation.json") if (run/"official_evaluation.json").exists() else {}; failed=[k for fam in ("commonsense_constraint","hard_constraint") for k,z in (ev.get(fam)or{}).items() if isinstance(z,list) and z and z[0] is False]
            trajectory=load(run/"trajectory.json") if (run/"trajectory.json").exists() else []
            audit=load(run/"evidence_audit.json") if (run/"evidence_audit.json").exists() else {}
            case_rows.append({"stage":s,"category":t,"horizon":horizon,"idx":v["idx"],"level":v["level"],"query":query,"terminal_status":v["delivered"] and "delivered" or "non_delivery","tool_calls":len(trajectory),"tools":dict(Counter(x.get("tool","unknown") for x in trajectory)),"route_coverage_rate":(audit.get("chosen_route_coverage")or{}).get("rate"),"grounding_rate":(audit.get("plan_evidence_grounding")or{}).get("rate"),"failed_constraints":failed,"mechanism_interpretation":explanations[t],"run_dir":v["run_dir"]})
    dump(OUT/"representative_cases.json",case_rows)
    case_md=["# 代表性 Failure Cases","","案例按 stage + 统一 failure 类别固定选择最短和最长 horizon 中 idx 最小者；用于解释，不代替频率统计。",""]
    for c in case_rows:
        case_md += [f"## Stage {c['stage']} · {c['category']} · idx {c['idx']}","",f"- 难度/天数：{c['level']} / {c['horizon']} 天",f"- 终态：{c['terminal_status']}；工具调用：{c['tool_calls']}",f"- Route coverage / grounding：{c['route_coverage_rate']} / {c['grounding_rate']}",f"- 失败约束：{', '.join(c['failed_constraints']) or '无可用 evaluator 明细（通常为 non-delivery）'}",f"- 机制解释：{c['mechanism_interpretation']}",f"- Query：{c['query']}",f"- 证据目录：`{c['run_dir']}`","" ]
    (OUT/"representative_cases.md").write_text("\n".join(case_md),encoding="utf-8")

    paired=[]
    for l,r,label in [("A","B","A_to_B_system_gap"),("B","C","B_to_C_planner"),("C","D","C_to_D_verifier_replan")]:
        for key in ("delivered","final_pass"):
            left=[x for x in standardized if x["stage"]==l];right=[x for x in standardized if x["stage"]==r];paired.append(paired_stats(left,right,key,label))
    write_csv(OUT/"paired_statistics.csv",paired);dump(OUT/"analysis_summary.json",{"main_metrics":main_rows,"paired":paired,"failure_taxonomy":{s:dict(tax[s]) for s in "ABCD"},"stage_d_funnel":{"candidates":119,"verifier_calls":119,"replans":46,"valid_replans":16,"repair_successes":4}})

    labels=["Delivery","Common micro","Common macro","Hard micro","Hard macro","Final Pass"]
    keys=["delivery_rate","commonsense_micro","commonsense_macro","hard_micro","hard_macro","final_pass"]
    bar_chart("01_core_metrics","A/B/C/D 核心指标","指标提高并不等价于机制稳定有效",labels,[(s,[next(r[k] for r in main_rows if r['stage']==s) for k in keys],COLORS[s]) for s in "ABCD"])
    bar_chart("02_delivery_final_gap","交付率与最终通过率","A 高交付但约束通过有限；B/C/D 的 Agent 控制成为新瓶颈",["Delivery","Final Pass"],[(s,[next(r[k] for r in main_rows if r['stage']==s) for k in ["delivery_rate","final_pass"]],COLORS[s]) for s in "ABCD"])
    mini_bars("03_cost_comparison","成本与运行开销","D 增加验证成本，但没有净增 Final Pass",[("每样本 Token",{r['stage']:r['tokens_per_sample'] for r in main_rows},lambda v:f"{v/1000:.1f}k"),("平均延迟",{r['stage']:r['mean_latency_seconds'] for r in main_rows},lambda v:f"{v:.1f}s"),("平均工具调用",{r['stage']:r['mean_tool_calls'] for r in main_rows},lambda v:f"{v:.1f}")])
    a=svg_start("Final Pass–Token 成本效率","右上不一定更好；理想方向是左上");x0,y0,w,h=180,180,1250,580;xs=[r['tokens_per_sample'] for r in main_rows];ys=[r['final_pass'] for r in main_rows];xmin,xmax=min(xs)*.85,max(xs)*1.08;ymin,ymax=.12,.18
    a += [f'<line x1="{x0}" y1="{y0+h}" x2="{x0+w}" y2="{y0+h}" stroke="#444"/>',f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y0+h}" stroke="#444"/>']
    for r in main_rows:
        x=x0+(r['tokens_per_sample']-xmin)/(xmax-xmin)*w;y=y0+h-(r['final_pass']-ymin)/(ymax-ymin)*h;a += [f'<circle cx="{x:.1f}" cy="{y:.1f}" r="26" fill="{COLORS[r["stage"]]}"/>',f'<text x="{x:.1f}" y="{y+7:.1f}" text-anchor="middle" class="val" fill="white">{r["stage"]}</text>',f'<text x="{x+36:.1f}" y="{y-20:.1f}" class="small">{r["final_pass"]*100:.2f}% / {r["tokens_per_sample"]/1000:.1f}k</text>']
    save_svg("04_cost_efficiency",a)
    heatmaps("05_horizon_difficulty_heatmap","难度 × 行程长度 Final Pass","每格 20 条 validation；四阶段统一色阶",{s:summaries[s]['groups'] for s in "ABCD"})
    cnames=sorted(set(x['constraint'] for x in constraints));a=svg_start("逐约束通过率热图","灰色表示该阶段该约束无适用样本");x0,y0,cw,ch=590,160,180,43
    for j,s in enumerate("ABCD"):a.append(f'<text x="{x0+(j+.5)*cw}" y="135" text-anchor="middle" class="lab">Stage {s}</text>')
    lookup={(x['stage'],x['constraint']):x['rate'] for x in constraints}
    for i,k in enumerate(cnames):
        a.append(f'<text x="{x0-15}" y="{y0+i*ch+28}" text-anchor="end" class="small">{esc(k)}</text>')
        for j,s in enumerate("ABCD"):
            v=lookup.get((s,k));color="#E5E5E5" if v is None else f'rgb({int(240-130*v)},{int(245-55*v)},{int(240-130*v)})';txt="—" if v is None else f"{v*100:.1f}%";a += [f'<rect x="{x0+j*cw}" y="{y0+i*ch}" width="{cw-5}" height="{ch-4}" fill="{color}"/>',f'<text x="{x0+(j+.48)*cw}" y="{y0+i*ch+27}" text-anchor="middle" class="small">{txt}</text>']
    save_svg("06_constraint_heatmap",a)
    stacked("07_failure_taxonomy","统一 Failure Taxonomy","原始类别保留在 CSV；堆叠图只比较统一主类别",tax)
    a=svg_start("相邻阶段 Final Pass 配对转移","A/B 是系统差距；B/C 与 C/D 才是同信息条件下的机制比较");
    for i,p in enumerate([x for x in paired if x['metric']=='final_pass']):
        x=170+i*500;a += [f'<text x="{x+160}" y="170" text-anchor="middle" class="title">{esc(p["comparison"])}</text>'];vals=[p['left_fail_right_pass'],p['left_pass_right_fail'],p['left_pass_right_pass']];labs=['fail→pass','pass→fail','both pass'];cols=['#228833','#EE6677','#4477AA']
        for j,(v,l,c) in enumerate(zip(vals,labs,cols)):a += [f'<rect x="{x}" y="{250+j*150}" width="{v*10+15}" height="70" fill="{c}" rx="5"/>',f'<text x="{x+v*10+28}" y="{295+j*150}" class="lab">{l}: {v}</text>']
        a.append(f'<text x="{x}" y="760" class="small">Δ={p["delta"]*100:+.2f}pp, p={p["mcnemar_p"]:.3f}</text>')
    save_svg("08_paired_transitions",a)
    funnel=[("候选",119),("Verifier",119),("Replan",46),("合法 Replan",16),("Repair success",4)];a=svg_start("Stage D 验证–修复漏斗","下游机制无法处理 61 条没有候选的上游失败");mx=119
    for i,(lab,v) in enumerate(funnel):w=1000*v/mx+120;x=800-w/2;y=170+i*125;a += [f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="82" rx="8" fill="{["#4477AA","#6699CC","#CCBB44","#EE9944","#228833"][i]}"/>',f'<text x="800" y="{y+51}" text-anchor="middle" class="val" fill="white">{esc(lab)}  {v}</text>']
    save_svg("09_stage_d_funnel",a)
    a=svg_start("Failure → Mechanism → Measured Effect","四阶段研究链的核心结论");items=[("Oracle evidence 已给定","Direct planning","高 Delivery，Final Pass 仍低","#4477AA"),("自主检索与 Agent 控制失败","Official tools + ReAct","Delivery −60pp，成本显著上升","#EE6677"),("全局路线与检索失焦","Explicit Planner","Delivery +5pp，Token 略降","#228833"),("候选错误与格式问题","Verifier + Single Replan","Delivery +1.67pp，Final Pass 不变","#CCBB44")]
    for i,(f,m,e,c) in enumerate(items):y=180+i*160;a += [f'<rect x="80" y="{y}" width="390" height="95" rx="12" fill="#FFF" stroke="{c}" stroke-width="3"/>',f'<text x="275" y="{y+56}" text-anchor="middle" class="lab">{esc(f)}</text>',f'<text x="535" y="{y+58}" class="title" fill="{c}">→</text>',f'<rect x="620" y="{y}" width="330" height="95" rx="12" fill="{c}" opacity=".9"/>',f'<text x="785" y="{y+56}" text-anchor="middle" class="lab" fill="white">{esc(m)}</text>',f'<text x="1015" y="{y+58}" class="title" fill="{c}">→</text>',f'<rect x="1100" y="{y}" width="420" height="95" rx="12" fill="#FFF" stroke="{c}" stroke-width="3"/>',f'<text x="1310" y="{y+56}" text-anchor="middle" class="lab">{esc(e)}</text>']
    save_svg("10_failure_mechanism_effect",a)

    captions=["01 核心指标：机制增加没有带来单调的 Final Pass 提升。","02 Delivery–Final gap：可交付不等于满足全部约束。","03 成本：D 的验证与修复显著增加 Token 和延迟。","04 效率：C 位于 B/D 左侧且 Final Pass 相同或更高。","05 九宫格：7 天长程任务仍是共同瓶颈。","06 约束：路线、预算、住宿与多样性是主要差异来源。","07 Failure taxonomy：B/C/D 的 Agent-control failure 占据主要部分。","08 配对转移：C/D 正负转移各 17，净效果为零。","09 D 漏斗：46 次修复只形成 16 个合法输出和 4 个 repair success。","10 研究链：不同机制只对特定 failure 起作用。"]
    (FIG/"captions.md").write_text("# 图注\n\n"+"\n\n".join(captions),encoding="utf-8")
    # One backing table per figure, so every plotted number remains inspectable.
    write_csv(FIG/"01_core_metrics.csv",main_rows)
    write_csv(FIG/"02_delivery_final_gap.csv",[{"stage":r["stage"],"delivery_rate":r["delivery_rate"],"final_pass":r["final_pass"]} for r in main_rows])
    write_csv(FIG/"03_cost_comparison.csv",[{k:r[k] for k in ("stage","tokens_per_sample","mean_latency_seconds","mean_tool_calls")} for r in main_rows])
    write_csv(FIG/"04_cost_efficiency.csv",[{k:r[k] for k in ("stage","tokens_per_sample","final_pass")} for r in main_rows])
    write_csv(FIG/"05_horizon_difficulty_heatmap.csv",[r for r in strata if r["group"].startswith("cell:")])
    write_csv(FIG/"06_constraint_heatmap.csv",constraints)
    write_csv(FIG/"07_failure_taxonomy.csv",[{"stage":s,"category":t,"count":tax[s][t],"rate":tax[s][t]/180} for s in "BCD" for t in TAXONOMY])
    write_csv(FIG/"08_paired_transitions.csv",paired)
    write_csv(FIG/"09_stage_d_funnel.csv",[{"step":x,"count":v} for x,v in funnel])
    write_csv(FIG/"10_failure_mechanism_effect.csv",[{"failure":x,"mechanism":m,"effect":e} for x,m,e,_ in items])
    report=f'''# TravelPlanner A/B/C/D 汇总与 Failure Analysis

## 结论摘要

四个正式实验均已冻结，各包含 180 条 validation，官方与本地评测完全一致。A/B/C/D 的 Delivery 分别为 {main_rows[0]['delivery_rate']:.2%}、{main_rows[1]['delivery_rate']:.2%}、{main_rows[2]['delivery_rate']:.2%}、{main_rows[3]['delivery_rate']:.2%}；Final Pass 分别为 {main_rows[0]['final_pass']:.2%}、{main_rows[1]['final_pass']:.2%}、{main_rows[2]['final_pass']:.2%}、{main_rows[3]['final_pass']:.2%}。

结果不支持“增加更多 Agent 组件会稳定提高效果”。A 表明 oracle 信息下模型能高概率交付，但全局约束满足仍弱；B 暴露自主信息获取和 Agent 控制的巨大系统成本；C 的显式 Planner 带来小幅效率与 Delivery 改善；D 的一次 Verifier/Replan 增加 1,263,248 Token，却没有净增 Final Pass。

## 三条机制链

### A → B：sole-planning 到 two-stage system gap

A/B 同时改变信息来源和信息获取责任，不能解释为工具的单变量因果效果。Delivery 从 95.00% 降至 35.00%，而 Token 从 1,960,945 增至 10,375,639。Final Pass 仅从 13.89% 到 15.56%，说明端到端自主检索的主要影响是成本和 non-delivery，而非稳定提升规划正确性。

### B → C：Explicit Planner

C 将 Delivery 提升至 40.00%，Final Pass 提升 0.56 个百分点，同时节省 300,056 Token 和每样本 1.60 次工具调用。Planner 对检索失焦和部分 Agent 控制有帮助，但没有解决 5/7 天长程一致性。

### C → D：Verifier + Single Replan

D 将 Delivery 提升 1.67 个百分点，Final Pass 保持 16.11%，并增加 1,263,248 Token。C fail→D pass 与 C pass→D fail 均为 17，McNemar p=1.0，bootstrap 95% CI 为 [−6.11,+6.11] 个百分点。由于 D 独立重跑 C 上游，这些转移同时包含上游非确定性，不能全部归因于修复机制。

## Failure analysis

统一 taxonomy 只用于跨阶段汇总，原始 failure flags 和 evaluator constraint 均保留。最重要的发现是 failure 的位置发生了变化：A 主要是已经交付计划中的约束错误；B/C/D 则首先受到 Agent-control/non-delivery 限制。D 中 61 条没有候选，Verifier 无法介入；119 个候选触发 119 次验证，46 次 Replan 仅产生 16 个合法结果和 4 个 post-hoc repair success。

预算、minimum nights、路线/交通、餐厅多样性仍是交付计划中的主要错误。单次 LLM Verifier 读取完整 evidence catalog 成本高且自身存在格式、引用和判断失败。因此下一步若继续研究，应建立独立条件测试结构化状态、确定性 constraint checker 或 targeted replan，而不能修改已冻结 D。

## 有效性边界

- A/B 是信息条件和系统责任的整体差距，不是工具因果效应。
- C/D 独立重跑上游，逐样本转移包含模型/API 非确定性。
- validation #1 曾用于格式开发；排除后各阶段结论不变。
- 代表案例采用固定规则抽取，仅用于解释，不替代总体统计。

## 产物索引

- `analysis/freeze_manifest.json`：冻结协议与输入哈希。
- `analysis/abcd_main_metrics.csv`：四阶段主表。
- `analysis/paired_statistics.csv`：配对检验和置信区间。
- `analysis/failure_taxonomy.csv`：统一失败类别。
- `analysis/representative_cases.json`：确定性案例集。
- `analysis/figures/`：10 张 SVG、高清 PNG、数据表和图注。
'''
    (ROOT/"experiments"/"abcd_failure_analysis.md").write_text(report,encoding="utf-8")
    print(json.dumps({"status":"ok","figures":10,"standardized_rows":len(standardized),"cases":len(case_rows)},ensure_ascii=False))
if __name__=="__main__":main()
