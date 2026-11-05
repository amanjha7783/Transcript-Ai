from app.core.config import settings


def get_client():
    if not settings.llm_api_key and not settings.llm_base_url:
        raise RuntimeError("LLM is not configured. Set LLM_API_KEY, or set LLM_BASE_URL for an OpenAI-compatible local server such as Ollama.")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("The openai Python package is not installed. Install backend/requirements.txt.") from exc
    return OpenAI(
        api_key=settings.llm_api_key or "ollama",
        base_url=settings.llm_base_url or None,
        timeout=120.0,
    )


def generate(system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
    client = get_client()
    response = client.chat.completions.create(
        model=settings.llm_model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("The language model returned an empty response.")
    return content.strip()
