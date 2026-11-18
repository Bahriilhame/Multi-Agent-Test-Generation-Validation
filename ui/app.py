"""Optional local Streamlit interface for generic SmartTest-AI runs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path, PurePosixPath

import streamlit as st

from ui.live_status import read_events, summarize_events

ROOT = Path(__file__).resolve().parents[1]

st.set_page_config(page_title="SmartTest-AI", page_icon="🧪", layout="wide")
st.title("SmartTest-AI")
st.caption("Analyse, génère et valide des tests Python dans un conteneur Docker isolé.")

with st.sidebar:
    model = st.text_input("Modèle Ollama", value=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"))
    iterations = st.slider("Nombre maximum d'itérations", 1, 5, 2)
    timeout = st.number_input("Timeout des tests (secondes)", min_value=10, max_value=1800, value=120)
    docker_image = st.text_input("Image Docker (pytest et dépendances préinstallés)", value="smarttest-runner:latest")
    min_score = st.slider("Score minimal d'acceptation", 0, 100, 70)

source_mode = st.radio("Projet", ["Dossier local", "Dossier sélectionné", "Archive ZIP", "Dépôt Git"], horizontal=True)
source_value = ""
if source_mode == "Dossier local":
    source_value = st.text_input("Chemin du projet sur cette machine", placeholder=r"C:\projets\mon-app")
elif source_mode == "Dossier sélectionné":
    selected_files = st.file_uploader("Sélectionner un dossier de projet", accept_multiple_files="directory", key="project_directory_upload")
    if selected_files:
        signature = tuple((file.name, len(file.getvalue())) for file in selected_files)
        if st.session_state.get("uploaded_directory_signature") != signature:
            upload_root = ROOT / "experiments" / "uploads" / uuid.uuid4().hex
            upload_root.mkdir(parents=True, exist_ok=False)
            for file in selected_files:
                relative = PurePosixPath(file.name.replace("\\", "/"))
                target = (upload_root / Path(*relative.parts)).resolve()
                if relative.is_absolute() or ".." in relative.parts or not target.is_relative_to(upload_root.resolve()):
                    raise ValueError(f"Unsafe uploaded project file path: {file.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(file.getvalue())
            st.session_state["uploaded_directory_signature"] = signature
            st.session_state["uploaded_directory_path"] = str(upload_root)
        source_value = st.session_state.get("uploaded_directory_path", "")
elif source_mode == "Archive ZIP":
    uploaded = st.file_uploader("Sélectionner une archive ZIP", type=["zip"])
    if uploaded:
        uploads = ROOT / "experiments" / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        archive_path = uploads / f"{uuid.uuid4().hex}_{Path(uploaded.name).name}"
        archive_path.write_bytes(uploaded.getvalue())
        source_value = str(archive_path)
else:
    source_value = st.text_input("URL Git HTTPS ou SSH", placeholder="https://github.com/org/repo.git")

active_run = st.session_state.get("active_run")
if st.button("Lancer l'analyse", type="primary", disabled=not source_value or active_run is not None):
    run_id = uuid.uuid4().hex
    cmd = [sys.executable, str(ROOT / "platform_cli.py"), "run", source_value,
           "--model", model, "--iterations", str(iterations), "--timeout", str(int(timeout)),
           "--min-quality", str(min_score), "--docker-image", docker_image, "--run-id", run_id]
    log_path = ROOT / "experiments" / "ui_logs" / f"{run_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(cmd, cwd=ROOT, stdout=log_file, stderr=subprocess.STDOUT)
    st.session_state["active_run"] = {"process": process, "run_id": run_id, "log_path": str(log_path)}
    st.session_state.pop("last_run", None)
    st.rerun()


def render_run_result(run: dict) -> None:
    """Render a completed run's report and captured CLI output."""
    return_code = run["return_code"]
    report_path = Path(run["report_path"]) if run.get("report_path") else None
    if return_code == 0 and report_path and report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        st.success(f"Workflow terminé — {report.get('status', 'statut inconnu')}")
        col1, col2, col3 = st.columns(3)
        col1.metric("Statut", report.get("status", "inconnu"))
        before = report.get("coverage_before")
        after = report.get("coverage_after")
        col2.metric("Couverture initiale", f"{before:.1f}%" if before is not None else "n/d")
        col3.metric("Couverture finale", f"{after:.1f}%" if after is not None else "n/d")
        st.json(report.get("critic", {}))
        st.write(f"Rapport : `{report_path}`")
    else:
        st.error(f"Le workflow s'est terminé avec le code {return_code}.")
    if run.get("output"):
        with st.expander("Sortie détaillée"):
            st.code(run["output"][-10000:] or "Aucune sortie", language="text")


def render_live_run() -> None:
    active = st.session_state.get("active_run")
    if not active:
        return
    process = active["process"]
    run_id = active["run_id"]
    matches = list((ROOT / "experiments" / "projects").glob(f"*/{run_id}/events.jsonl"))
    events = read_events(matches[0]) if matches else []
    steps = summarize_events(events)

    if process.poll() is not None:
        output = Path(active["log_path"]).read_text(encoding="utf-8", errors="replace") if Path(active["log_path"]).exists() else ""
        reports = list((ROOT / "experiments" / "projects").glob(f"*/{run_id}/report.json"))
        st.session_state["last_run"] = {
            "run_id": run_id,
            "return_code": process.returncode,
            "output": output,
            "report_path": str(reports[0]) if reports else None,
        }
        st.session_state.pop("active_run", None)
        st.rerun()

    st.subheader("Progression du workflow")
    if not steps:
        st.info("Préparation du projet (copie locale, extraction ZIP ou clonage Git)…")
        st.progress(0, text="Préparation du projet")
        return

    current = next((step for step in reversed(steps) if step["status"] == "running"), None)
    if current:
        iteration_text = f" — itération {current['iteration'] + 1}" if current["node"] in {"generator", "validation", "critic"} else ""
        st.info(f"Étape en cours : **{current['label']}**{iteration_text}")
    completed = sum(step["status"] in {"completed", "failed"} for step in steps)
    st.progress(min(1.0, completed / max(1, len(steps))), text=f"{completed} étape(s) terminée(s)")
    for step in steps:
        marker = {"completed": "✅", "running": "🔄", "failed": "❌", "pending": "⏳"}[step["status"]]
        iteration_text = f" · itération {step['iteration'] + 1}" if step["node"] in {"generator", "validation", "critic"} else ""
        detail = f" — {step['error']}" if step.get("error") else ""
        st.write(f"{marker} {step['label']}{iteration_text}{detail}")


if st.session_state.get("active_run"):
    @st.fragment(run_every="1s")
    def live_run_fragment():
        render_live_run()

    live_run_fragment()
elif st.session_state.get("last_run"):
    render_run_result(st.session_state["last_run"])

st.divider()
st.subheader("Runs récents")
run_reports = sorted((ROOT / "experiments" / "projects").glob("*/*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
for path in run_reports[:10]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        st.write(f"**{path.parent.parent.name} / {path.parent.name}** — {report.get('status', 'inconnu')} — score critique: {(report.get('critic') or {}).get('score', 'n/a')}")
    except (OSError, json.JSONDecodeError):
        continue
