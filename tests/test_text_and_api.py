"""Text helpers, safety rules and the FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient

from rag.models import PatientContext
from rag.safety import assess_safety, recommendation_checks
from rag.text_utils import critical_terms, has_negation, split_recommendations, term_in_text
from tests.helpers import verifier_with


# ----------------------------------------------------------------------------- text utils
def test_critical_terms_find_drugs_and_doses():
    terms = critical_terms("Take Amoxicillin 500 mg twice daily for 5 days, avoid ibuprofen")
    assert {"amoxicillin", "ibuprofen", "500 mg", "twice daily", "5 days"} <= set(terms)


def test_term_matching_handles_plurals_and_doses():
    assert term_in_text("antibiotic", "do not offer antibiotics")
    assert term_in_text("500 mg", "dose is 500mg daily")
    assert not term_in_text("doxycycline", "amoxicillin only")


def test_negation_detection():
    assert has_negation("Do not offer an antibiotic") and not has_negation("Offer an antibiotic")


def test_split_recommendations_keeps_advice_drops_questions():
    reply = "I'm sorry you feel unwell. How long have you had it? You should rest and drink plenty of fluids. Consider seeing a doctor if it gets worse."
    recs = split_recommendations(reply)
    assert any("rest and drink" in r for r in recs) and any("Consider seeing" in r for r in recs)
    assert all(not r.endswith("?") for r in recs)


# ----------------------------------------------------------------------------- safety rules
def test_red_flags_from_triage_engine_are_reused():
    s = assess_safety(PatientContext(symptoms=["slurred speech"]), [])
    assert s.urgent_escalation and "slurred speech" in " ".join(s.emergency_reasons)


def test_safety_never_downgrades_upstream_emergency():
    s = assess_safety(PatientContext(symptoms=["cough"]), ["rest"], triage={"level": "Emergency"})
    assert s.urgent_escalation


def test_urgent_triage_sets_note_but_not_emergency():
    s = assess_safety(PatientContext(symptoms=["cough"]), ["rest"], triage={"level": "Urgent"})
    assert s.prompt_assessment_indicated and not s.urgent_escalation and s.notes


def test_false_reassurance_flagged_when_info_missing():
    p = PatientContext(symptoms=["cough"])
    s = assess_safety(p, [], triage={"level": "Urgent"})
    _, concerns = recommendation_checks("There is nothing to worry about, no need to see a doctor.", p, s)
    assert any("false reassurance" in c for c in concerns)


def test_pregnancy_status_requested_for_drug_advice_to_women_of_childbearing_age():
    p = PatientContext(age=30, sex="female", symptoms=["cough"], allergies=[], medications=[])
    missing, _ = recommendation_checks("Take amoxicillin 500 mg", p, assess_safety(p, []))
    assert "pregnancy status" in missing


# ----------------------------------------------------------------------------- API
@pytest.fixture()
def client(retriever, monkeypatch):
    import main
    import rag.verifier as rv
    monkeypatch.setattr(rv, "_instance", verifier_with(retriever, heuristic=True))
    main.app.dependency_overrides[main.get_current_user] = lambda: {"email": "tester@example.test"}
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def test_verify_endpoint_returns_structured_result(client):
    body = {"patient_context": {"age": 34, "symptoms": ["cough"], "duration": "4 days", "allergies": [], "medical_history": []},
            "recommendations": ["Advise adequate fluid intake and rest for acute cough."]}
    for path in ("/api/verify-guideline", "/verify-guideline"):
        r = client.post(path, json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["verification_status"] == "supported"
        assert data["recommendations"][0]["evidence"][0]["source_url"].startswith("https://")


def test_verify_endpoint_validates_input(client):
    assert client.post("/api/verify-guideline", json={"patient_context": {"age": -5}, "recommendations": ["x"]}).status_code == 422
    assert client.post("/api/verify-guideline", json={"patient_context": {}, "recommendations": []}).status_code == 422


def test_verify_endpoint_requires_login():
    import main
    main.app.dependency_overrides.clear()
    r = TestClient(main.app).post("/api/verify-guideline", json={"patient_context": {}, "recommendations": ["x"]})
    assert r.status_code == 401


def test_internal_errors_do_not_leak_patient_data(client, monkeypatch):
    import rag.verifier as rv

    class Boom:
        def verify(self, *a, **k):
            raise RuntimeError("secret patient detail: chest pain")

    monkeypatch.setattr(rv, "_instance", Boom())
    r = client.post("/api/verify-guideline", json={"patient_context": {"symptoms": ["chest pain"]}, "recommendations": ["rest"]})
    assert r.status_code == 500 and "secret" not in r.text and "chest pain" not in r.text


def test_status_endpoint_lists_documents(client):
    data = client.get("/api/guidelines/status").json()
    assert data["chunks"] > 0 and any("Synthetic" in d["title"] for d in data["documents"])


def test_existing_triage_verify_function_still_works():
    from guideline_verifier import verify
    assert verify({"level": "Routine", "reason": "x"}, []) == {"level": "Routine", "reason": "x"}
    assert verify({"level": "Routine", "reason": "x"}, ["appendicitis"])["level"] == "Emergency"
