import json, os, random, time
from symptom_extractor import extract_structured

VIGNETTES_FILE = "data/vignettes.json"

class PatientSimulator:
    def __init__(self):
        os.makedirs("data", exist_ok=True)
        # load existing vignettes if exist
        if os.path.exists(VIGNETTES_FILE):
            with open(VIGNETTES_FILE, "r", encoding="utf-8") as f:
                self.vignettes = json.load(f)
        else:
            self.vignettes = []

    def generate_patient(self):
        names = ["John Doe", "Jane Smith", "Alice", "Bob", "Charlie"]
        complaints = ["chest pain", "headache", "fever", "cough", "stomach ache"]
        severities = ["mild", "moderate", "severe"]
        vitals_list = [
            {"hr": 80, "bp": "120/80", "temp": 36.8},
            {"hr": 100, "bp": "130/85", "temp": 37.5},
            {"hr": 140, "bp": "90/60", "temp": 39.0},
        ]

        patient = {
            "id": int(time.time() * 1000),
            "name": random.choice(names),
            "age": random.randint(20, 70),
            "chief_complaint": random.choice(complaints),
            "severity": random.choice(severities),
            "vitals": random.choice(vitals_list),
            "associated_symptoms": random.sample(
                ["nausea", "dizziness", "fatigue", "shortness of breath"],
                k=random.randint(0, 2)
            ),
            "history": random.choice([
                "No significant past medical history.",
                "History of hypertension.",
                "History of diabetes."
            ])
        }
        return patient

    def save_patient_to_vignettes(self, patient):
        self.vignettes.append(patient)
        with open(VIGNETTES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.vignettes, f, indent=2, ensure_ascii=False)

    def get_random_patient(self):
        if not self.vignettes:
            patient = self.generate_patient()
            self.save_patient_to_vignettes(patient)
        return random.choice(self.vignettes)

    def simulate_conversation(self, patient, num_turns=3):
        conversation_lines = [
            f"Patient: Hi, I am {patient['name']}, {patient['age']} years old.",
            f"Chief Complaint: {patient['chief_complaint']}",
            f"History: {patient['history']}",
            f"Vitals: {json.dumps(patient['vitals'])}",
            f"Symptoms: {', '.join(patient.get('associated_symptoms', []))}"
        ]

        follow_ups = [
            "Can you describe the severity of your symptoms on a scale of 1-10?",
            "When did the symptoms start?",
            "Do you have any past medical conditions?",
            "Are you currently taking any medications?",
            "Have you noticed any triggers or relieving factors?"
        ]

        for i in range(min(num_turns, len(follow_ups))):
            conversation_lines.append(f"Doctor: {follow_ups[i]}")
            conversation_lines.append(f"Patient: {random.choice(['Mild', 'Moderate', 'Severe', 'Not sure'])}")

        conversation_text = "\n".join(conversation_lines)
        structured = extract_structured(conversation_text)

        message_history = []
        for line in conversation_text.split("\n"):
            if line.startswith("Patient:"):
                message_history.append({"role": "user", "content": line[len("Patient: "):]})
            elif line.startswith("Doctor:"):
                message_history.append({"role": "assistant", "content": line[len("Doctor: "):]})

        return message_history, structured


# For testing outside FastAPI
if __name__ == "__main__":
    sim = PatientSimulator()
    p = sim.generate_patient()
    sim.save_patient_to_vignettes(p)
    print("Patient simulator ran successfully! Generated patient:")
    print(json.dumps(p, indent=2))
    msg_history, structured = sim.simulate_conversation(p)
    print("\nSimulated conversation (message history):")
    print(json.dumps(msg_history, indent=2))
