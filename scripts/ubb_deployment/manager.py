"""Product-neutral materialization of verified M1 artifacts into deployments."""
from __future__ import annotations
import hashlib, json, os, pathlib, shutil, tempfile
from dataclasses import dataclass
import ubb_archive

class DeploymentError(Exception): pass

@dataclass(frozen=True)
class DeploymentManifest:
    schema_version:int; service_id:str; integration_id:str; release:str|None; artifact_id:str; artifact_sha256:str; derived_artifact_id:str|None; materialized_at:str; materialization_mode:str; target_root:str; tree_sha256:str; state_scope:str="per_deployment"; shared_state_id:str|None=None
    def to_dict(self): return self.__dict__.copy()

def _tree_digest(root):
    h=hashlib.sha256()
    for p in sorted(x for x in pathlib.Path(root).rglob("*") if x.is_file()):
        rel=p.relative_to(root).as_posix(); h.update(rel.encode()+b"\0"); h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()

class DeploymentManager:
    def __init__(self, archive_root, deployment_root, *, now=None): self.archive=pathlib.Path(archive_root).resolve(); self.root=pathlib.Path(deployment_root).resolve(); self.now=now
    def _metadata(self, artifact_id):
        path=self.archive/"metadata"/f"{artifact_id}.json"
        try: doc=json.loads(path.read_text())
        except (OSError,ValueError): raise DeploymentError("preserved artifact metadata unavailable")
        if doc.get("rights",{}).get("install_locally") is False: raise DeploymentError("artifact is not permitted for local installation")
        digest=doc.get("artifact",{}).get("sha256")
        if not digest: raise DeploymentError("artifact SHA-256 missing")
        obj=ubb_archive.object_path(self.archive,digest)
        if not obj.exists(): raise DeploymentError("preserved artifact object missing")
        if hashlib.sha256(obj.read_bytes()).hexdigest()!=digest: raise DeploymentError("preserved artifact verification failed")
        return doc,obj,digest
    def materialize(self, service_id, integration_id, artifact_id, target_root, *, release=None, derived_artifact_id=None, mode="copy", state_scope="per_deployment", shared_state_id=None):
        if state_scope not in ("per_deployment","shared"): raise DeploymentError("invalid state scope")
        if state_scope=="shared" and not shared_state_id: raise DeploymentError("shared state requires an ID")
        target=pathlib.Path(target_root).resolve()
        if target==self.archive or self.archive in target.parents: raise DeploymentError("deployment cannot be inside preservation archive")
        doc,obj,digest=self._metadata(artifact_id); staging=pathlib.Path(tempfile.mkdtemp(prefix="deployment.",dir=self.root.parent)); published=False
        try:
            payload=staging/"assets"; payload.mkdir(parents=True)
            if obj.is_dir(): shutil.copytree(obj,payload,dirs_exist_ok=True)
            else: shutil.copy2(obj,payload/obj.name)
            target.parent.mkdir(parents=True,exist_ok=True); manifest=DeploymentManifest(1,service_id,integration_id,release,artifact_id,digest,derived_artifact_id,(self.now() if self.now else __import__('datetime').datetime.now(__import__('datetime').timezone.utc)).isoformat(),mode,str(target),_tree_digest(payload),state_scope,shared_state_id)
            (staging/"deployment-manifest.json").write_text(json.dumps(manifest.to_dict(),sort_keys=True,indent=2)+"\n")
            if target.exists(): raise DeploymentError("deployment target already exists")
            os.replace(staging,target); published=True; return manifest
        finally:
            if not published: shutil.rmtree(staging,ignore_errors=True)
    def show(self, service_id):
        path=self.root/service_id/"deployment-manifest.json"
        try:return json.loads(path.read_text())
        except (OSError,ValueError): return None
    def list(self): return tuple(self.show(p.name) for p in sorted(self.root.iterdir()) if p.is_dir() and self.show(p.name)) if self.root.exists() else ()
    def verify(self, service_id):
        doc=self.show(service_id)
        if not doc: raise DeploymentError("deployment manifest unavailable")
        target=pathlib.Path(doc["target_root"]).resolve()
        if not target.exists() or _tree_digest(target/"assets")!=doc["tree_sha256"]: raise DeploymentError("deployment tree or digest mismatch")
        self._metadata(doc["artifact_id"]); return True
    def provenance(self, service_id):
        doc=self.show(service_id)
        if not doc: raise DeploymentError("deployment unavailable")
        metadata,_digest,_=self._metadata(doc["artifact_id"]); return {"deployment":doc,"artifact":metadata}
