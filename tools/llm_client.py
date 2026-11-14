import os
from dotenv import load_dotenv
from langchain_ollama import ChatOllama

load_dotenv()

MODEL_NAME = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5-coder:7b"
)

BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434"
)


def get_llm():
    """Initialise le modèle IA local avec Ollama."""

    return ChatOllama(
        model=MODEL_NAME,
        base_url=BASE_URL,
        temperature=0
    )


def ask_llm(prompt: str) -> str:
    """Envoie un prompt au modèle et retourne sa réponse."""

    llm = get_llm()
    response = llm.invoke(prompt)

    return response.content