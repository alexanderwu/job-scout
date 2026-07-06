"""Deterministic match explanations: which skills line up, which don't.

PLAN.md's LLM decision applies here: explanations *lean on keyword/
skill overlap (cheap, deterministic)*, with an LLM only ever phrasing
them (Phase 4). The reasoning a user trusts is "you both mention
Python, Kubernetes, and Airflow; the job also wants Scala, you don't" —
which needs set intersection, not a language model. Deterministic also
means testable: the same resume and job always explain identically.

The skill vocabulary is curated rather than learned. Alternatives:
- TF-IDF top terms: no vocabulary to maintain, but surfaces junk
  ("stakeholders", "fast-paced") that erodes trust in the whole list.
- NER/skill-extraction models: heavy dependency for marginal gain at
  this scale.
A ~150-term curated list with alias folding covers the tech-role
vocabulary that matters and is trivially extendable — adding a skill is
a one-line diff with an obvious review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# skill -> canonical display form. Keys are matched case-insensitively
# as whole words (with +/#/. treated as part of the word: c++, c#,
# node.js survive tokenization).
_CANON: dict[str, str] = {
    # languages
    "python": "Python",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "go": "Go",
    "golang": "Go",
    "rust": "Rust",
    "c": "C",
    "c++": "C++",
    "cpp": "C++",
    "c#": "C#",
    "ruby": "Ruby",
    "php": "PHP",
    "swift": "Swift",
    "kotlin": "Kotlin",
    "scala": "Scala",
    "r": "R",
    "julia": "Julia",
    "matlab": "MATLAB",
    "perl": "Perl",
    "elixir": "Elixir",
    "haskell": "Haskell",
    "sql": "SQL",
    "bash": "Bash",
    # data & ML
    "pandas": "pandas",
    "numpy": "NumPy",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "keras": "Keras",
    "jax": "JAX",
    "xgboost": "XGBoost",
    "spark": "Spark",
    "pyspark": "Spark",
    "hadoop": "Hadoop",
    "airflow": "Airflow",
    "dbt": "dbt",
    "kafka": "Kafka",
    "flink": "Flink",
    "snowflake": "Snowflake",
    "databricks": "Databricks",
    "bigquery": "BigQuery",
    "redshift": "Redshift",
    "mlops": "MLOps",
    "mlflow": "MLflow",
    "ray": "Ray",
    "llm": "LLMs",
    "llms": "LLMs",
    "rag": "RAG",
    "embeddings": "embeddings",
    "transformers": "transformers",
    "nlp": "NLP",
    "computer vision": "computer vision",
    "opencv": "OpenCV",
    "etl": "ETL",
    "elt": "ETL",
    "data warehouse": "data warehousing",
    "data warehousing": "data warehousing",
    "data modeling": "data modeling",
    "a/b testing": "A/B testing",
    "ab testing": "A/B testing",
    "tableau": "Tableau",
    "looker": "Looker",
    "power bi": "Power BI",
    # web / backend
    "react": "React",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "vue": "Vue",
    "angular": "Angular",
    "svelte": "Svelte",
    "node": "Node.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "django": "Django",
    "flask": "Flask",
    "fastapi": "FastAPI",
    "rails": "Rails",
    "spring": "Spring",
    "graphql": "GraphQL",
    "rest": "REST APIs",
    "grpc": "gRPC",
    "websocket": "WebSockets",
    "websockets": "WebSockets",
    "html": "HTML",
    "css": "CSS",
    "tailwind": "Tailwind",
    # databases & infra
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "sqlite": "SQLite",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "elasticsearch": "Elasticsearch",
    "dynamodb": "DynamoDB",
    "cassandra": "Cassandra",
    "neo4j": "Neo4j",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "helm": "Helm",
    "linux": "Linux",
    "git": "Git",
    "github actions": "GitHub Actions",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "jenkins": "Jenkins",
    "prometheus": "Prometheus",
    "grafana": "Grafana",
    "datadog": "Datadog",
    "kinesis": "Kinesis",
    "rabbitmq": "RabbitMQ",
    "serverless": "serverless",
    "lambda": "AWS Lambda",
    "microservices": "microservices",
    "distributed systems": "distributed systems",
    # practice & role words that carry real signal
    "agile": "Agile",
    "scrum": "Scrum",
    "tdd": "TDD",
    "observability": "observability",
    "oncall": "on-call",
    "on-call": "on-call",
    "security": "security",
    "oauth": "OAuth",
    "leadership": "leadership",
    "mentoring": "mentoring",
    "product management": "product management",
    "stakeholder management": "stakeholder management",
}

# Multi-word keys need phrase matching; single tokens use one combined
# regex pass. Both built once at import.
_PHRASES = sorted((k for k in _CANON if " " in k), key=len, reverse=True)
_PHRASE_RES = [
    (re.compile(rf"(?<![\w+#]){re.escape(p)}(?![\w+#])", re.IGNORECASE), p) for p in _PHRASES
]
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#./-]*")


def extract_skills(text: str) -> set[str]:
    """Canonical skills mentioned in the text."""
    lowered = text.casefold()
    found: set[str] = set()
    for phrase_re, phrase in _PHRASE_RES:
        if phrase_re.search(lowered):
            found.add(_CANON[phrase])
    for token in _TOKEN_RE.findall(lowered):
        token = token.rstrip(".,")  # sentence punctuation glued to a token
        if token in _CANON:
            found.add(_CANON[token])
    return found


@dataclass
class MatchExplanation:
    """Why a job matched — and what's missing (Phase 4's skill gap)."""

    overlapping: list[str]  # in the job AND the resume
    missing: list[str]  # in the job, not the resume

    def summary(self) -> str:
        if not self.overlapping:
            return "matched on overall similarity (no specific shared skills detected)"
        text = "shared skills: " + ", ".join(self.overlapping)
        if self.missing:
            text += " — job also wants: " + ", ".join(self.missing)
        return text


def explain_match(resume_skills: set[str], job_text: str) -> MatchExplanation:
    job_skills = extract_skills(job_text)
    return MatchExplanation(
        overlapping=sorted(job_skills & resume_skills),
        missing=sorted(job_skills - resume_skills),
    )
