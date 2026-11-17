import os
import logging
import httpx
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
REQUEST_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "180"))
RETRY_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_RETRY_TIMEOUT_SECONDS", "360"))
MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "1"))
logger = logging.getLogger(__name__)


def get_llm(timeout_seconds: float | None = None):
    """Initialise le modèle IA local avec Ollama."""

    return ChatOllama(
        model=MODEL_NAME,
        base_url=BASE_URL,
        temperature=0,
        client_kwargs={"timeout": timeout_seconds or REQUEST_TIMEOUT_SECONDS},
    )


def ask_llm(prompt: str) -> str:
    """Envoie un prompt au modèle et retourne sa réponse."""

    timeouts = [REQUEST_TIMEOUT_SECONDS]
    timeouts.extend([RETRY_TIMEOUT_SECONDS] * MAX_RETRIES)
    last_error = None

    for attempt, timeout_seconds in enumerate(timeouts, start=1):
        llm = get_llm(timeout_seconds=timeout_seconds)
        try:
            response = llm.invoke(prompt)
            return response.content
        except httpx.ReadTimeout as error:
            last_error = error
            logger.warning(
                "Timeout Ollama à la tentative %s/%s après %s s (%s)",
                attempt, len(timeouts), timeout_seconds, MODEL_NAME,
            )
            if attempt == len(timeouts):
                break
        except Exception:
            logger.exception("Échec de l'appel Ollama (%s, %s)", MODEL_NAME, BASE_URL)
            raise

    raise TimeoutError(
        f"Ollama n'a pas répondu après {len(timeouts)} tentative(s). "
        f"Dernier délai : {timeouts[-1]} secondes. Vérifie le serveur, "
        "le modèle chargé et la mémoire disponible."
    ) from last_error
