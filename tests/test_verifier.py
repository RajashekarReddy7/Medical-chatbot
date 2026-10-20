"""Verification engine behaviour with synthetic patients and a scripted (mocked) LLM."""
import json

import pytest
import requests

from rag.judges import HeuristicJudge, JudgeError, OllamaClient, OllamaJudge, parse_judgement
from rag.models import PatientContext
from rag.retriever import RetrievalError
from rag.verifier import GuidelineVerifier
from tests.helpers import FakeLLM, verifier_with

ADULT = PatientContext(age=34, symptoms=["cough"], duration="4 days", allergies=[], medications=[], medical_history=[])


def J(**kw):
    base = {"status": "insufficient_evidence", "reason": "r", "supporting": [], "contradicting": [], "quotes": {},
            "missing_information": [], "safety_concerns": [], "conflicting_sources": False}
    base.update(kw)
    return json.dumps(base)


def ids_for(retriever, rec, patient=ADULT):
    """Passage ids (E1..En) the judge will see for `rec`, so mocked answers can cite real ones."""
    res = retriever.retrieve(rec, patient)
    return res.passages


# ------------------------------------------------------------------ 1. supported
def test_supported_recommendation_with_real_citation(retriever):
    rec = "Advise adequate fluid intake and rest for acute cough."
    v = verifier_with(retriever, heuristic=True).verify(ADULT, [rec])
    r = v.recommendations[0]
    assert r.status == "supported" and v.verification_status == "supported"
    assert r.evidence and r.evidence[0].role == "supports"
    assert r.evidence[0].page_number >= 1 and r.evidence[0].source_url.startswith("https://")
    assert "fluid" in r.evidence[0].quoted_text.lower()
    assert r.recommendation == rec, "the original recommendation must be returned untouched"


def test_supported_via_mocked_llm(retriever):
    rec = "Advise adequate fluid intake and rest for acute cough."
    passages = ids_for(retriever, rec)
    idx = next(i for i, p in enumerate(passages, 1) if "fluid intake" in p.chunk.text)
    llm = FakeLLM(J(status="supported", reason="Self-care advice matches.", supporting=[f"E{idx}"],
                    quotes={f"E{idx}": "Advise adequate fluid intake and rest for acute cough."}))
    r = verifier_with(retriever, llm).verify(ADULT, [rec]).recommendations[0]
    assert r.status == "supported"
    assert r.evidence[0].quoted_text == "Advise adequate fluid intake and rest for acute cough."
    assert "ADULT" not in llm.prompts[0] and "fluid intake" in llm.prompts[0]


# ------------------------------------------------------------------ 2. conflict
def test_conflict_with_guideline_detected(retriever):
    rec = "Offer an antibiotic to adults with acute cough who are otherwise well."
    r = verifier_with(retriever, heuristic=True).verify(ADULT, [rec]).recommendations[0]
    assert r.status == "potential_conflict"
    assert any(e.role == "contradicts" and "Do not offer an antibiotic" in e.quoted_text for e in r.evidence)
    assert r.requires_clinician_review


# ------------------------------------------------------------------ 3. no evidence / 9. empty retrieval
def test_no_relevant_evidence_abstains(retriever):
    r = verifier_with(retriever, heuristic=True).verify(ADULT, ["Apply a warm compress to the knee."]).recommendations[0]
    assert r.status == "insufficient_evidence" and r.evidence == []
    assert r.requires_clinician_review


def test_llm_not_called_when_nothing_retrieved(retriever):
    llm = FakeLLM(J(status="supported"))
    verifier_with(retriever, llm).verify(ADULT, ["Apply a warm compress to the knee."])
    assert llm.prompts == []


# ------------------------------------------------------------------ 4. insufficient patient context
def test_missing_patient_info_blocks_plain_support_for_medication(retriever):
    rec = "Amoxicillin is preferred in pregnancy."
    patient = PatientContext(symptoms=["cough"], pregnant=True)           # no age, allergies, medications
    r = verifier_with(retriever, heuristic=True).verify(patient, [rec]).recommendations[0]
    assert r.status == "escalate_for_review"
    assert {"patient age", "allergy history"} <= set(r.missing_information)
    assert any("Medication advice" in c for c in r.safety_concerns)


# ------------------------------------------------------------------ 5. exceptions / contraindications
def test_contraindication_text_is_visible_to_judge(retriever):
    rec = "Prescribe doxycycline for a pregnant woman with acute cough."
    passages = ids_for(retriever, rec, PatientContext(age=28, symptoms=["cough"], pregnant=True))
    idx = next(i for i, p in enumerate(passages, 1) if "Do not offer doxycycline" in p.chunk.text)
    assert "penicillin allergy" in passages[idx - 1].chunk.text            # exception kept with the rule
    llm = FakeLLM(J(status="potential_conflict", reason="Guideline says not to offer doxycycline in pregnancy.",
                    contradicting=[f"E{idx}"]))
    r = verifier_with(retriever, llm).verify(PatientContext(age=28, symptoms=["cough"], pregnant=True, allergies=[], medications=[]), [rec]).recommendations[0]
    assert r.status == "potential_conflict" and r.evidence[0].role == "contradicts"


# ------------------------------------------------------------------ 6. conflicting sources
def test_conflicting_sources_between_two_documents(retriever):
    rec = "Offer a delayed antibiotic prescription to adults with acute cough."
    passages = ids_for(retriever, rec)
    a = next(i for i, p in enumerate(passages, 1) if "Do not offer an antibiotic" in p.chunk.text)
    b = next(i for i, p in enumerate(passages, 1) if "delayed antibiotic" in p.chunk.text)
    llm = FakeLLM(J(status="supported", supporting=[f"E{b}"], contradicting=[f"E{a}"], conflicting_sources=True))
    r = verifier_with(retriever, llm).verify(ADULT, [rec]).recommendations[0]
    assert r.status == "potential_conflict"
    assert r.conflicting_sources and {"supports", "contradicts"} <= {e.role for e in r.evidence}
    assert len({e.publisher for e in r.evidence}) == 2
    assert any("disagree" in c for c in r.safety_concerns)


# ------------------------------------------------------------------ 7. outdated source
def test_stale_source_is_flagged_not_hidden(retriever):
    rec = "Gargle with warm salty water for relief of acute sore throat."
    v = verifier_with(retriever, heuristic=True).verify(PatientContext(age=40, symptoms=["sore throat"]), [rec])
    r = v.recommendations[0]
    assert r.status == "supported" and r.evidence[0].source_stale
    assert any("older" in c for c in r.safety_concerns) and r.requires_clinician_review
    assert any("older" in lim for lim in v.limitations)


# ------------------------------------------------------------------ 10-11. LLM failures
@pytest.mark.parametrize("bad", ["not json at all", "", "{\"status\": \"definitely_fine\"}", "[1,2,3]"])
def test_invalid_llm_output_never_becomes_supported(retriever, bad):
    llm = FakeLLM(bad)
    v = verifier_with(retriever, llm).verify(ADULT, ["Advise adequate fluid intake and rest for acute cough."])
    r = v.recommendations[0]
    assert r.status == "insufficient_evidence" and v.degraded
    assert "NOT verified" in r.reason and len(llm.prompts) == 2           # one retry, then give up


def test_json_wrapped_in_prose_is_tolerated():
    j = parse_judgement('Sure! ```json\n{"status": "insufficient_evidence", "reason": "x"}\n``` hope that helps')
    assert j.status == "insufficient_evidence"


@pytest.mark.parametrize("exc,msg", [(requests.ConnectionError("down"), "not reachable"), (requests.Timeout("slow"), "timed out")])
def test_ollama_unavailable_or_timeout(retriever, monkeypatch, exc, msg):
    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(requests, "post", boom)
    judge = OllamaJudge(llm=OllamaClient(retriever.settings))
    v = GuidelineVerifier(retriever=retriever, judge=judge, settings=retriever.settings).verify(
        ADULT, ["Advise adequate fluid intake and rest for acute cough."])
    r = v.recommendations[0]
    assert r.status == "insufficient_evidence" and v.degraded
    assert msg in r.reason and any(msg in e for e in v.errors)


# ------------------------------------------------------------------ 12. knowledge base unavailable
def test_knowledge_base_outage_is_not_silently_supported(retriever):
    class DownRetriever:
        settings = retriever.settings
        def retrieve(self, *a, **k):
            raise RetrievalError("knowledge base unavailable: simulated")

    v = GuidelineVerifier(retriever=DownRetriever(), judge=HeuristicJudge(), settings=retriever.settings).verify(
        ADULT, ["Advise adequate fluid intake and rest for acute cough."])
    assert v.recommendations[0].status == "insufficient_evidence" and v.degraded
    assert "could not be queried" in v.recommendations[0].reason


# ------------------------------------------------------------------ 14. emergency
def test_emergency_is_escalated_without_llm_or_retrieval(retriever):
    class Exploding:
        name = "exploding"
        def judge(self, *a):
            raise AssertionError("the judge must not be needed for emergency escalation")

    class DownRetriever:
        settings = retriever.settings
        def retrieve(self, *a, **k):
            raise RetrievalError("down")

    patient = PatientContext(age=55, symptoms=["chest pain", "shortness of breath"])
    v = GuidelineVerifier(retriever=DownRetriever(), judge=Exploding(), settings=retriever.settings).verify(
        patient, ["Rest at home and drink fluids."])
    assert v.urgent_escalation and v.verification_status == "escalate_for_review"
    assert v.recommendations[0].status == "escalate_for_review"
    assert any("emergency" in n.lower() for n in v.overall_safety_notes)


def test_upstream_emergency_triage_cannot_be_downgraded(retriever):
    v = verifier_with(retriever, heuristic=True).verify(
        ADULT, ["Advise adequate fluid intake and rest for acute cough."], triage={"level": "Emergency", "reason": "upstream"})
    assert v.urgent_escalation and v.recommendations[0].status == "escalate_for_review"


def test_emergency_phrase_inside_recommendation_escalates(retriever):
    v = verifier_with(retriever, heuristic=True).verify(ADULT, ["Go to hospital if you start coughing up blood."])
    assert v.urgent_escalation


def test_vital_sign_thresholds_reuse_triage_engine(retriever):
    v = verifier_with(retriever, heuristic=True).verify(
        PatientContext(age=40, symptoms=["cough"], vitals={"temp": "40.5"}), ["Advise rest."])
    assert v.urgent_escalation


# ------------------------------------------------------------------ 15. fabricated citations
def test_fabricated_passage_id_is_rejected(retriever):
    llm = FakeLLM(J(status="supported", reason="trust me", supporting=["E99"]))
    r = verifier_with(retriever, llm).verify(ADULT, ["Advise adequate fluid intake and rest for acute cough."]).recommendations[0]
    assert r.status == "insufficient_evidence" and r.evidence == []
    assert any("E99" in c for c in r.citation_issues) and r.requires_clinician_review


def test_fabricated_quote_is_replaced_with_real_text(retriever):
    rec = "Advise adequate fluid intake and rest for acute cough."
    passages = ids_for(retriever, rec)
    idx = next(i for i, p in enumerate(passages, 1) if "fluid intake" in p.chunk.text)
    llm = FakeLLM(J(status="supported", supporting=[f"E{idx}"], quotes={f"E{idx}": "Drink 4 litres of water hourly."}))
    r = verifier_with(retriever, llm).verify(ADULT, [rec]).recommendations[0]
    assert r.status == "supported"
    assert "4 litres" not in r.evidence[0].quoted_text and "fluid" in r.evidence[0].quoted_text.lower()
    assert any("not found verbatim" in c for c in r.citation_issues)


def test_drug_or_dose_absent_from_evidence_cannot_be_supported(retriever):
    rec = "Offer ciprofloxacin as an antibiotic to adults with acute cough."
    patient = PatientContext(age=40, symptoms=["cough"], allergies=[], medications=[])
    passages = ids_for(retriever, rec, patient)
    assert passages, "test needs some retrieved passage to cite"
    llm = FakeLLM(J(status="supported", supporting=["E1"]))
    r = verifier_with(retriever, llm).verify(patient, [rec]).recommendations[0]
    assert r.status == "insufficient_evidence"
    assert "ciprofloxacin" in r.reason


def test_claimed_conflict_without_citation_is_downgraded(retriever):
    llm = FakeLLM(J(status="potential_conflict", reason="feels wrong"))
    r = verifier_with(retriever, llm).verify(ADULT, ["Advise adequate fluid intake and rest for acute cough."]).recommendations[0]
    assert r.status == "insufficient_evidence"


# ------------------------------------------------------------------ 16. population out of scope
def test_guideline_for_other_population_is_not_applied(retriever):
    rec = "Give paracetamol 15 mg per kg to children under 5 years with fever who are distressed."
    adult_patient = PatientContext(age=40, symptoms=["fever"], allergies=[], medications=[])
    r = verifier_with(retriever, heuristic=True).verify(adult_patient, [rec]).recommendations[0]
    assert r.status == "insufficient_evidence"
    assert "population" in r.reason.lower()


def test_in_scope_population_is_used(retriever):
    rec = "Give paracetamol 15 mg per kg to children under 5 years with fever who are distressed."
    child = PatientContext(age=3, symptoms=["fever"], allergies=[], medications=[])
    r = verifier_with(retriever, heuristic=True).verify(child, [rec]).recommendations[0]
    assert r.status == "supported"


# ------------------------------------------------------------------ aggregation / output contract
def test_overall_status_is_worst_of_all(retriever):
    v = verifier_with(retriever, heuristic=True).verify(
        ADULT, ["Advise adequate fluid intake and rest for acute cough.",
                "Offer an antibiotic to adults with acute cough who are otherwise well."])
    assert [r.status for r in v.recommendations] == ["supported", "potential_conflict"]
    assert v.verification_status == "potential_conflict"
    assert v.limitations and v.judge == "heuristic"


def test_result_matches_documented_json_shape(retriever):
    data = verifier_with(retriever, heuristic=True).verify(ADULT, ["Advise rest for acute cough."]).model_dump()
    assert {"verification_status", "recommendations", "overall_safety_notes", "urgent_escalation", "limitations"} <= set(data)
    rec = data["recommendations"][0]
    assert {"recommendation", "status", "reason", "evidence", "missing_information", "safety_concerns", "requires_clinician_review"} <= set(rec)
    json.dumps(data)   # must be JSON serialisable
