"""Skill extraction and match explanations."""

from jobscout.matching.explain import explain_match, extract_skills


def test_extracts_plain_and_awkward_tokens() -> None:
    text = "We use Python, C++, C#, Node.js and PostgreSQL on AWS (k8s)."
    skills = extract_skills(text)
    assert {"Python", "C++", "C#", "Node.js", "PostgreSQL", "AWS", "Kubernetes"} <= skills


def test_aliases_fold_to_canonical() -> None:
    assert extract_skills("golang and postgres and sklearn") == extract_skills(
        "Go, PostgreSQL, scikit-learn"
    )


def test_word_boundaries_prevent_false_hits() -> None:
    # "scala" inside "scalable" or "r" inside words must not match.
    skills = extract_skills("highly scalable architecture for real users")
    assert "Scala" not in skills
    assert "R" not in skills


def test_phrases_match_across_spaces() -> None:
    skills = extract_skills("experience with distributed systems and A/B testing")
    assert "distributed systems" in skills
    assert "A/B testing" in skills


def test_explanation_splits_overlap_and_gap() -> None:
    resume_skills = extract_skills("Python, SQL, Airflow")
    explanation = explain_match(resume_skills, "Wants Python, SQL, Spark, and Kafka")
    assert explanation.overlapping == ["Python", "SQL"]
    assert explanation.missing == ["Kafka", "Spark"]
    summary = explanation.summary()
    assert "Python" in summary
    assert "job also wants" in summary


def test_no_overlap_has_honest_summary() -> None:
    explanation = explain_match(set(), "Wants Figma")
    assert "no specific shared skills" in explanation.summary()
