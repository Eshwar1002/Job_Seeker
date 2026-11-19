"""Resume parsing agent: text extraction + SLM structured extraction with heuristic fallback."""
import io
import logging
import re
from datetime import datetime

from .. import llm

logger = logging.getLogger(__name__)

SKILL_ALIASES: dict[str, list[str]] = {
    "python": ["python"], "java": ["java"], "c++": ["c++", "cpp"], "javascript": ["javascript", "js"],
    "typescript": ["typescript"], "sql": ["sql"], "r": [" r ", "r programming"],
    "machine learning": ["machine learning", "ml", "scikit-learn", "sklearn", "scikit learn"],
    "deep learning": ["deep learning", "neural network"],
    "nlp": ["nlp", "natural language processing"],
    "computer vision": ["computer vision", "opencv", "yolo", "image processing"],
    "llm": ["llm", "large language model", "gpt", "llama", "mistral", "gemini", "claude"],
    "genai": ["genai", "generative ai", "gen ai"],
    "langchain": ["langchain"], "langgraph": ["langgraph"], "llamaindex": ["llamaindex", "llama index"],
    "rag": ["rag", "retrieval augmented", "retrieval-augmented"],
    "huggingface": ["hugging face", "huggingface", "transformers"],
    "pytorch": ["pytorch", "torch"], "tensorflow": ["tensorflow", "keras"],
    "pandas": ["pandas"], "numpy": ["numpy"], "scipy": ["scipy"],
    "fine-tuning": ["fine-tuning", "fine tuning", "finetuning", "lora", "qlora", "peft", "sft", "rlhf", "dpo"],
    "prompt engineering": ["prompt engineering", "prompt design"],
    "ai agents": ["agentic", "ai agent", "multi-agent", "multi agent", "autogen", "crewai", "mcp"],
    "embeddings": ["embedding", "sentence transformer", "sentence-transformer"],
    "vector database": ["vector database", "vector db", "chromadb", "chroma", "pinecone", "faiss", "weaviate", "qdrant", "milvus", "pgvector"],
    "mlops": ["mlops", "mlflow", "kubeflow", "model monitoring", "model registry"],
    "model deployment": ["model deployment", "model serving", "bentoml", "triton", "vllm", "onnx", "tensorrt", "tfserving", "torchserve"],
    "fastapi": ["fastapi"], "flask": ["flask"], "django": ["django"], "streamlit": ["streamlit"], "gradio": ["gradio"],
    "docker": ["docker", "containerization"], "kubernetes": ["kubernetes", "k8s"],
    "aws": ["aws", "amazon web services", "sagemaker", "ec2", "s3", "lambda"],
    "azure": ["azure", "azure ml"], "gcp": ["gcp", "google cloud", "vertex ai", "bigquery"],
    "airflow": ["airflow"], "spark": ["spark", "pyspark"], "kafka": ["kafka"],
    "etl": ["etl", "data pipeline", "data engineering"],
    "postgresql": ["postgresql", "postgres"], "mongodb": ["mongodb", "mongo"], "mysql": ["mysql"],
    "redis": ["redis"], "elasticsearch": ["elasticsearch", "opensearch"],
    "git": ["git", "github", "gitlab"], "ci/cd": ["ci/cd", "cicd", "jenkins", "github actions"],
    "linux": ["linux", "bash", "shell scripting"],
    "rest api": ["rest api", "restful", "api development"], "graphql": ["graphql"],
    "react": ["react", "reactjs"], "node.js": ["node.js", "nodejs"],
    "statistics": ["statistics", "statistical", "a/b test", "hypothesis testing"],
    "data visualization": ["tableau", "power bi", "powerbi", "matplotlib", "seaborn", "plotly"],
    "weights & biases": ["wandb", "weights & biases", "weights and biases"],
    "databricks": ["databricks"], "snowflake": ["snowflake"],
    "evaluation": ["llm evaluation", "model evaluation", "guardrails", "langsmith", "ragas"],
    "speech": ["speech recognition", "whisper", "asr", "tts"],
    "recommendation systems": ["recommendation", "recommender", "collaborative filtering"],
    "time series": ["time series", "forecasting", "arima", "prophet"],
    "optimization": ["optimization", "or-tools", "linear programming"],
    "web scraping": ["scraping", "beautifulsoup", "selenium", "playwright", "scrapy"],
    "celery": ["celery", "rabbitmq", "task queue"],
    "langsmith": ["langsmith"], "ollama": ["ollama"],
}

_EXP_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp)?", re.I
)
_EXP_MONTHS_RE = re.compile(r"(\d+)\s*(?:years?|yrs?)\.?\s*(?:and\s*)?(\d+)\s*(?:months?|mos?)", re.I)
_DATE_RANGE_RE = re.compile(
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}|\d{1,2}/\d{4}|\d{4})\s*[-–—to]+\s*"
    r"((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}|\d{1,2}/\d{4}|\d{4}|present|current|till date)",
    re.I,
)
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        import pdfplumber

        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    if name.endswith(".docx"):
        import docx

        document = docx.Document(io.BytesIO(data))
        parts = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    return data.decode("utf-8", errors="ignore")


def _parse_date(token: str) -> datetime | None:
    token = token.strip().lower()
    if token in ("present", "current", "till date"):
        return datetime.now()
    m = re.match(r"([a-z]{3})[a-z]*\.?\s*(\d{4})", token)
    if m and m.group(1) in _MONTHS:
        return datetime(int(m.group(2)), _MONTHS[m.group(1)], 1)
    m = re.match(r"(\d{1,2})/(\d{4})", token)
    if m:
        return datetime(int(m.group(2)), int(m.group(1)), 1)
    m = re.match(r"(\d{4})", token)
    if m:
        return datetime(int(m.group(1)), 1, 1)
    return None


def _experience_from_dates(text: str) -> float:
    total_months = 0.0
    for start, end in _DATE_RANGE_RE.findall(text):
        d1, d2 = _parse_date(start), _parse_date(end)
        if d1 and d2 and d2 >= d1:
            total_months += (d2.year - d1.year) * 12 + (d2.month - d1.month)
    return round(total_months / 12, 1)


def detect_skills(text: str) -> list[str]:
    low = " " + text.lower() + " "
    found = []
    for canonical, aliases in SKILL_ALIASES.items():
        for alias in aliases:
            pattern = r"(?<![a-z0-9+#])" + re.escape(alias) + r"(?![a-z0-9+#])"
            if re.search(pattern, low):
                found.append(canonical)
                break
    return found


def heuristic_parse(text: str) -> dict:
    email = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    phone = re.search(r"(?:\+91[\s-]?)?[6-9]\d{9}\b", text)
    name = ""
    for line in text.splitlines():
        line = line.strip()
        if line and not re.search(r"[@\d/\\|]", line) and 2 <= len(line.split()) <= 4 and len(line) < 60:
            name = line
            break

    years = 0.0
    m = _EXP_MONTHS_RE.search(text)
    if m:
        years = int(m.group(1)) + int(m.group(2)) / 12
    else:
        candidates = [float(x) for x in _EXP_RE.findall(text) if float(x) <= 40]
        summary_match = re.search(r"(?:experience|exp)[^\n]{0,80}?(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", text, re.I)
        if summary_match:
            years = float(summary_match.group(1))
        elif candidates:
            years = max(candidates)
    if years == 0.0:
        years = _experience_from_dates(text)

    role = ""
    role_re = re.compile(
        r"((?:senior |junior |lead |associate )?(?:ai|ml|machine learning|data|software|python|genai|nlp|research|backend|full stack)"
        r"[a-z &]*(?:engineer|scientist|developer|analyst|researcher))", re.I)
    m = role_re.search(text)
    if m:
        role = m.group(1).strip().title()

    return {
        "name": name,
        "email": email.group(0) if email else "",
        "phone": phone.group(0) if phone else "",
        "current_role": role,
        "experience_years": round(years, 1),
        "skills": detect_skills(text),
        "work_history": [],
        "education": [],
        "projects": [],
        "certifications": [],
    }


PARSE_SYSTEM = """You are a resume parsing engine. Extract structured data from the resume text.
Return ONLY valid JSON with exactly these keys:
{
  "name": str, "email": str, "phone": str,
  "current_role": str (most recent job title),
  "experience_years": number (total professional experience in years, e.g. 1.2 for 1 year 2 months; exclude internships only if full-time roles exist),
  "skills": [str] (technical skills, normalized lowercase),
  "work_history": [{"title": str, "company": str, "start": str, "end": str, "summary": str}],
  "education": [{"degree": str, "institution": str, "year": str}],
  "projects": [{"name": str, "description": str, "tech": [str]}],
  "certifications": [str]
}
Do not invent information. Use empty strings/lists for missing data."""


def parse_resume(filename: str, data: bytes) -> tuple[str, dict]:
    text = extract_text(filename, data)
    if not text.strip():
        raise ValueError("Could not extract any text from the resume file")

    base = heuristic_parse(text)
    parsed = llm.chat_json(PARSE_SYSTEM, f"Resume text:\n\n{text[:12000]}", prefer="local")
    if parsed:
        for key in base:
            val = parsed.get(key)
            if val not in (None, "", []):
                base[key] = val
        base["parse_method"] = "llm+heuristic"
    else:
        base["parse_method"] = "heuristic"

    if isinstance(base.get("experience_years"), str):
        try:
            base["experience_years"] = float(re.search(r"\d+(?:\.\d+)?", base["experience_years"]).group(0))
        except Exception:
            base["experience_years"] = 0.0
    base["skills"] = sorted({s.lower().strip() for s in base.get("skills", []) if isinstance(s, str) and s.strip()})
    return text, base