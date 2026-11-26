"""Run one focused Qwen design-reasoning pass over the five dev pilot posters."""
from __future__ import annotations
import argparse, base64, json, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
MODEL = "qwen3.5:9b-q4_K_M"

def request_json(url: str, payload: dict | None = None, timeout: int = 300) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type":"application/json"}, method="GET" if data is None else "POST")
    with urlopen(request, timeout=timeout) as response: return json.loads(response.read().decode("utf-8"))

def prompt_for(knowledge: list[dict], brief: str | None = None) -> str:
    curriculum = "\n".join(f"[{x['knowledge_id']}] {x['title']}: {x['summary']}" for x in knowledge)
    context = (f"User-provided design brief (context, not visual evidence): {brief}. Assess likely fit against this brief while distinguishing brief-derived claims from visible evidence."
               if brief else "No brief is supplied: intended purpose and priority are unknown.")
    return f'''Analyze this poster as a connected composition. Return only valid JSON. Quote text only when clearly legible. {context} Do not infer audience, intent, brand identity, cultural meaning, or fill categories without direct evidence (a visible logo alone may support an identity observation, not an audience claim). Every observation needs at least one evidence ID. Every interpretation/judgment cites evidence IDs; every relationship names connected observations. Distinguish physical size, apparent prominence, and semantic importance. Reading flow is plausible, not universal. State uncertainty. Recommendations may be empty; do not invent defects. Apply curriculum only when it helps explain this image; retrieval alone is not evidence.
Curriculum entries: {curriculum}
Return this JSON shape (IDs unique; refs valid; confidence 0..1; use empty arrays when unsupported):
{{"evidence":[{{"evidence_id":"ev1","description":"directly visible feature","location":"plain-language location","confidence":0.0}}],"observations":[{{"observation_id":"obs1","text":"image-specific observation","role":"likely role or unknown","evidence_refs":["ev1"],"confidence":0.0}}],"relationships":[{{"relationship_id":"rel1","subject_refs":["obs1"],"relation":"contrast/alignment/grouping/overlap/scale/etc","object_refs":["obs2"],"effect":"what interaction does","interpretation":"why it matters here","principle":"applied principle or null","curriculum_refs":["knowledge-id"],"observation_refs":["obs1","obs2"],"evidence_refs":["ev1"],"confidence":0.0}}],"hierarchy":{{"apparent_order":[{{"observation_ref":"obs1","rank":1,"prominence_evidence":"visible attention cues","confidence":0.0}}],"reading_flow":[{{"sequence":["obs1","obs2"],"rationale":"visible cues","confidence":0.0}}],"intended_priority":"unknown without brief"}},"evaluations":[{{"evaluation_id":"eval1","dimension":"hierarchy/composition/typography/colour/cohesion/clarity/relationships","judgment":"effective/mixed/weak/not_assessable","finding":"contextual judgment","impact":"likely effect","observation_refs":["obs1"],"relationship_refs":["rel1"],"evidence_refs":["ev1"],"curriculum_refs":["knowledge-id"],"confidence":0.0,"uncertainty":"low/medium/high/unknown"}}],"recommendations":[{{"recommendation_id":"rec1","priority":"critical/meaningful/optional/subjective","change":"specific refinement","reason":"issue/opportunity","expected_impact":"likely result","evaluation_refs":["eval1"],"evidence_refs":["ev1"],"confidence":0.0}}],"specialists":[{{"area":"typography/composition/colour/imagery/communication","finding":"specific image finding","evidence_refs":["ev1"],"relationship_refs":["rel1"],"curriculum_refs":["knowledge-id"],"confidence":0.0}}],"uncertainties":["what cannot be established"]}}
At most 3 evidence, 4 observations, 2 relationships, 2 evaluations, 1 recommendation, 1 specialist finding. Keep each field under 12 words. Evaluation may say already effective. Use curriculum refs only for applied principles.'''


def analyze_image_bytes(root: Path, image: dict, image_bytes: bytes, *, brief: str | None = None,
                        base_url: str = "http://127.0.0.1:11434", timeout: int = 300,
                        on_stage=None) -> tuple[dict, dict, float]:
    """Run the same Phase 5 Qwen prompt and v1.2 validator for a newly uploaded image."""
    from curriculum.retrieve import retrieve
    from annotations.phase5_intelligence import make_annotation

    root = root.resolve()
    if on_stage: on_stage("checking_model")
    tags = request_json(base_url.rstrip("/") + "/api/tags", timeout=min(timeout, 10))
    if MODEL not in {item.get("name") for item in tags.get("models", [])}:
        raise RuntimeError(f"Required Ollama model is unavailable: {MODEL}")
    if on_stage: on_stage("preparing_visual_input")
    query = (brief + " " if brief else "") + "visual hierarchy composition typography colour contrast design critique relationships"
    if on_stage: on_stage("applying_curriculum")
    curriculum_error = None
    try:
        knowledge = retrieve(root, query, limit=8)
    except Exception as exc:
        knowledge, curriculum_error = [], f"Curriculum retrieval unavailable; analysis proceeded without curriculum: {type(exc).__name__}."
    curriculum_refs = [item["knowledge_id"] for item in knowledge]
    prompt = prompt_for(knowledge, brief)
    if on_stage: on_stage("analyzing_with_qwen")
    started = time.perf_counter()
    response = request_json(base_url.rstrip("/") + "/api/generate", {
        "model": MODEL, "prompt": prompt,
        "images": [base64.b64encode(image_bytes).decode("ascii")],
        "stream": False, "format": "json", "think": False,
        "options": {"temperature": 0, "num_ctx": 8192, "num_predict": 4500},
    }, timeout=timeout)
    elapsed_ms = (time.perf_counter() - started) * 1000
    if response.get("done_reason") == "length":
        raise ValueError("Qwen stopped at its output limit; the analysis is incomplete.")
    text = response.get("response", "")
    if not text.strip():
        raise ValueError("Qwen returned an empty analysis.")
    if on_stage: on_stage("validating_analysis")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Qwen returned malformed JSON: {exc.msg} at character {exc.pos}.") from exc
    annotation = make_annotation(image, parsed, curriculum_refs=curriculum_refs, model=MODEL,
                                 elapsed_ms=elapsed_ms, brief=brief, prompt_version="design-intelligence-v1.1")
    if curriculum_error:
        annotation["uncertainties"].append(curriculum_error)
    return annotation, response, elapsed_ms

def run(root: Path, limit: int = 5, timeout: int = 300, force: bool = False, reprocess: bool = False) -> list[dict]:
    from curriculum.retrieve import retrieve
    from annotations.phase5_intelligence import make_annotation
    root=root.resolve()
    tags=request_json("http://127.0.0.1:11434/api/tags",timeout=10)
    if MODEL not in {x.get("name") for x in tags.get("models",[])}: raise RuntimeError(f"Required model unavailable; no substitution permitted: {MODEL}")
    batch=json.loads((root/"evaluation/datasets/batch_001_manifest.json").read_text(encoding="utf-8"))
    samples=[s for s in batch["samples"] if s["dataset_split"]=="development"][:limit]
    images={row["image_id"]:row for row in (json.loads(line) for line in (root/"manifests/image_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip())}
    raw_dir,ann_dir=root/"phase5_pilot_outputs/predictions",root/"phase5_pilot_outputs/annotations"
    raw_dir.mkdir(parents=True,exist_ok=True); ann_dir.mkdir(parents=True,exist_ok=True)
    knowledge=retrieve(root,"visual hierarchy composition typography colour contrast design critique relationships",limit=8)
    refs=[x["knowledge_id"] for x in knowledge]; prompt=prompt_for(knowledge); records=[]
    for sample in samples:
        image=images[sample["image_id"]]; raw_path=raw_dir/f"{image['image_id']}.json"; ann_path=ann_dir/f"{image['image_id']}.json"
        if not force and not reprocess and raw_path.exists() and ann_path.exists():
            old=json.loads(raw_path.read_text(encoding="utf-8")); records.append(old); print(f"Preserved {image['image_id']}: {old['status']}"); continue
        if not force and raw_path.exists() and (reprocess or not ann_path.exists()):
            old=json.loads(raw_path.read_text(encoding="utf-8"))
            if old.get("parsed_response"):
                try:
                    ann=make_annotation(image,old["parsed_response"],curriculum_refs=refs,model=MODEL,elapsed_ms=old["elapsed_ms"])
                    ann_path.write_text(json.dumps(ann,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
                    old["status"],old["error"]="ok",None
                except Exception as exc:
                    old["status"],old["error"]="error",f"{type(exc).__name__}: {exc}"
                raw_path.write_text(json.dumps(old,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
                records.append(old); print(f"Reprocessed saved response {image['image_id']}: {old['status']}"); continue
        t0=time.perf_counter(); parsed=None; response=None
        try:
            data=(root/image["relative_path"]).read_bytes()
            response=request_json("http://127.0.0.1:11434/api/generate",{"model":MODEL,"prompt":prompt,"images":[base64.b64encode(data).decode("ascii")],"stream":False,"format":"json","think":False,"options":{"temperature":0,"num_ctx":8192,"num_predict":4500}},timeout)
            elapsed=(time.perf_counter()-t0)*1000; parsed=json.loads(response.get("response",""))
            if response.get("done_reason")=="length": raise ValueError("generation ended at token limit; output is incomplete")
            annotation=make_annotation(image,parsed,curriculum_refs=refs,model=MODEL,elapsed_ms=elapsed)
            ann_path.write_text(json.dumps(annotation,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); status,error="ok",None
        except Exception as exc:
            elapsed=(time.perf_counter()-t0)*1000; status,error="error",f"{type(exc).__name__}: {exc}"
        record={"schema_version":"1.0.0","run_id":"phase5_pilot","image_id":image["image_id"],"input_sha256":image["sha256"],"model":MODEL,"prompt_version":"design-intelligence-v1.0","timestamp":datetime.now(timezone.utc).isoformat(timespec="seconds"),"elapsed_ms":round(elapsed,2),"status":status,"done_reason":response.get("done_reason") if response else None,"raw_response":response.get("response") if response else None,"parsed_response":parsed,"error":error}
        raw_path.write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); records.append(record)
        print(f"{image['image_id']}: {status} ({elapsed/1000:.1f}s)"+(f" — {error}" if error else ""))
    summary={"schema_version":"1.0.0","run_id":"phase5_pilot","model":MODEL,"prompt_version":"design-intelligence-v1.0","images_requested":len(samples),"successful":sum(x["status"]=="ok" for x in records),"failed":sum(x["status"]!="ok" for x in records),"total_elapsed_ms":round(sum(x["elapsed_ms"] for x in records),2),"curriculum_refs_retrieved":refs,"records":[{"image_id":x["image_id"],"status":x["status"],"elapsed_ms":x["elapsed_ms"]} for x in records]}
    (raw_dir/"run_manifest.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); return records

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--root",type=Path,default=ROOT); parser.add_argument("--limit",type=int,default=5); parser.add_argument("--timeout",type=int,default=300); parser.add_argument("--force",action="store_true",help="rerun inference and replace this phase's pilot outputs"); parser.add_argument("--reprocess",action="store_true",help="rebuild annotations from saved JSON responses without another inference call"); args=parser.parse_args(); run(args.root,max(0,min(args.limit,5)),args.timeout,args.force,args.reprocess)
