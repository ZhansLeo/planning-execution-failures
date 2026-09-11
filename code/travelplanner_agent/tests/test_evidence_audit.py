import unittest

from travelplanner_agent.evidence_audit import build_evidence_audit, finalize_evidence_audit


def step(number, tool, arguments, data, *, ok=True, empty=False):
    return {"step": number, "tool": tool, "arguments": arguments, "status": "success" if ok else "error",
            "tool_latency_seconds": .1, "observation": {"ok": ok, "empty": empty, "data": data}}


class EvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"idx": 1, "query": "q", "plan": [
            {"days": 1, "current_city": "from A to B", "transportation": "Flight Number: F1, from A to B, Departure Time: 08:00, Arrival Time: 09:00",
             "breakfast": "Cafe, B", "attraction": "Museum, B", "lunch": "Cafe, B", "dinner": "Cafe, B", "accommodation": "Room, B"},
            {"days": 2, "current_city": "from B to A", "transportation": "self-driving, from B to A, duration: 1 hour, distance: 10 km, cost: 1",
             "breakfast": "Cafe, B", "attraction": "Museum, B", "lunch": "Cafe, B", "dinner": "Cafe, B", "accommodation": "-"},
        ]}
        self.trajectory = [
            step(1, "restaurant_search", {"city": "B"}, [{"Name": "Cafe"}]),
            step(2, "attraction_search", {"city": "B"}, [{"Name": "Museum"}]),
            step(3, "accommodation_search", {"city": "B"}, [{"NAME": "Room"}]),
            step(4, "flight_search", {"origin": "A", "destination": "B", "departure_date": "2022-01-01"}, [{"Flight Number": "F1"}]),
            step(5, "distance_matrix", {"origin": "B", "destination": "A", "mode": "self-driving"}, "self-driving, from B to A"),
        ]
        self.reference = {"Restaurants in B": [], "Attractions in B": [], "Accommodations in B": [],
                          "Flight from A to B on 2022-01-01": [], "Self-driving from B to A": "x"}

    def test_complete_grounded_plan_and_oracle_alignment(self):
        audit = build_evidence_audit(trajectory=self.trajectory, submission=self.plan,
                                     reference_information=self.reference, terminal_reason="final_response")
        self.assertTrue(audit["chosen_route_coverage"]["sufficient"])
        self.assertTrue(audit["plan_evidence_grounding"]["fully_grounded"])
        self.assertEqual(audit["oracle_alignment"]["rate"], 1.0)
        evaluation = {"final_pass": True, "commonsense_constraint": {"is_valid_information_in_sandbox": [True, None]}}
        finalize_evidence_audit(audit, delivered=True, evaluation=evaluation)
        self.assertEqual(audit["primary_failure_category"], "success")

    def test_missing_search_precedes_grounding_failure(self):
        audit = build_evidence_audit(trajectory=self.trajectory[:1], submission=self.plan,
                                     reference_information=self.reference, terminal_reason="final_response")
        finalize_evidence_audit(audit, delivered=True, evaluation={"final_pass": False})
        self.assertEqual(audit["primary_failure_category"], "evidence_insufficient_for_chosen_plan")
        self.assertTrue(audit["failure_flags"]["evidence_utilization_or_grounding_failure"])

    def test_non_delivery_has_highest_priority(self):
        audit = build_evidence_audit(trajectory=[], submission=None,
                                     reference_information=self.reference, terminal_reason="context_limit")
        finalize_evidence_audit(audit, delivered=False, evaluation=None)
        self.assertEqual(audit["primary_failure_category"], "non_delivery_or_agent_control")

    def test_entity_name_preserves_meaningful_trailing_period(self):
        plan = {"plan": [{"days": 1, "current_city": "B", "transportation": "-",
                          "breakfast": "-", "attraction": "-", "lunch": "-", "dinner": "-",
                          "accommodation": "Room with apt., B"}]}
        trajectory = [step(1, "accommodation_search", {"city": "B"}, [{"NAME": "Room with apt."}])]
        audit = build_evidence_audit(trajectory=trajectory, submission=plan,
                                     reference_information={}, terminal_reason="final_response")
        self.assertTrue(audit["plan_evidence_grounding"]["items"][0]["supported"])


if __name__ == "__main__":
    unittest.main()
