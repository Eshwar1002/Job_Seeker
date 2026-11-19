from pathlib import Path

from app.agents.resume_parser import detect_skills, extract_text, heuristic_parse, parse_resume

FIXTURE = Path(__file__).parent / "fixtures" / "sample_resume.txt"


def test_extract_text_txt():
    text = extract_text("resume.txt", FIXTURE.read_bytes())
    assert "Eshwar" in text


def test_extract_text_plain_fallback():
    assert extract_text("notes.txt", b"hello world") == "hello world"


def test_heuristic_experience_months():
    p = heuristic_parse("AI Engineer with 1 year 2 months of experience building LLM apps.")
    assert p["experience_years"] == 1.2


def test_heuristic_experience_summary():
    p = heuristic_parse("Summary: 3+ years of experience in machine learning.\nPython, PyTorch")
    assert p["experience_years"] == 3.0


def test_heuristic_contact_and_role():
    text = "Eshwar Kumar\nAI Engineer\neshwar@example.com\n+91 9876543210\n1 year 2 months experience"
    p = heuristic_parse(text)
    assert p["name"] == "Eshwar Kumar"
    assert p["email"] == "eshwar@example.com"
    assert "9876543210" in p["phone"]
    assert "Engineer" in p["current_role"]


def test_detect_skills_aliases():
    skills = detect_skills("Built RAG pipelines with LangChain and LangGraph, fine-tuned via LoRA. Python, PyTorch.")
    for expected in ("rag", "langchain", "langgraph", "fine-tuning", "python", "pytorch"):
        assert expected in skills, f"missing {expected} in {skills}"


def test_detect_skills_no_false_positive():
    assert "java" not in detect_skills("JavaScript and TypeScript expert")


def test_parse_resume_fallback_without_llm():
    text, parsed = parse_resume("sample_resume.txt", FIXTURE.read_bytes())
    assert parsed["experience_years"] == 1.2
    assert "langgraph" in parsed["skills"]
    assert parsed.get("parse_method") in ("heuristic", "llm+heuristic", "llm")