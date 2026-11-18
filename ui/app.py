"""Optional local Streamlit interface for generic SmartTest-AI runs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path, PurePosixPath

import streamlit as st

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

if st.button("Lancer l'analyse", type="primary", disabled=not source_value):
    cmd = [sys.executable, str(ROOT / "platform_cli.py"), "run", source_value,
           "--model", model, "--iterations", str(iterations), "--timeout", str(int(timeout)),
           "--min-quality", str(min_score), "--docker-image", docker_image]
    process = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    st.session_state["run_process"] = process
    st.session_state["run_source"] = source_value
    st.info("Workflow démarré. Utilise le bouton Actualiser pour vérifier son état.")

process = st.session_state.get("run_process")
if process is not None:
    if st.button("Actualiser l'état"):
        st.rerun()
    return_code = process.poll()
    if return_code is None:
        st.warning(f"Exécution en cours (PID {process.pid}). Le modèle Ollama peut prendre quelques minutes.")
    else:
        output, _ = process.communicate()
        st.session_state.pop("run_process", None)
        st.code(output[-10000:] or "Aucune sortie", language="text")
        if return_code == 0:
            matches = list((ROOT / "experiments" / "projects").glob("*/*/report.json"))
            latest = max(matches, key=lambda path: path.stat().st_mtime) if matches else None
            if latest:
                report = json.loads(latest.read_text(encoding="utf-8"))
                col1, col2, col3 = st.columns(3)
                col1.metric("Statut", report.get("status", "inconnu"))
                col2.metric("Couverture initiale", f"{report.get('coverage_before', 0):.1f}%")
                col3.metric("Couverture finale", f"{(report.get('coverage_after') or 0):.1f}%")
                st.json(report.get("critic", {}))
                st.write(f"Rapport : `{latest}`")
        else:
            st.error(f"Le workflow a terminé avec le code {return_code}.")

st.divider()
st.subheader("Runs récents")
run_reports = sorted((ROOT / "experiments" / "projects").glob("*/*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
for path in run_reports[:10]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        st.write(f"**{path.parent.parent.name} / {path.parent.name}** — {report.get('status', 'inconnu')} — score critique: {(report.get('critic') or {}).get('score', 'n/a')}")
    except (OSError, json.JSONDecodeError):
        continue
