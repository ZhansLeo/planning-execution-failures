import unittest

import pandas as pd

from travelplanner_agent.react_tools import OfficialToolbox


class FakeTool:
    def __init__(self, result): self.result = result
    def run(self, *args): return self.result


class ToolAdapterTests(unittest.TestCase):
    def toolbox(self, name, result):
        box = OfficialToolbox.__new__(OfficialToolbox)
        box._tools = {name: FakeTool(result)}
        return box

    def test_official_returned_exception_is_error(self):
        result = self.toolbox("city_search", ValueError("Invalid State")).execute(
            "city_search", {"state": "Nowhere"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "ValueError")

    def test_official_no_result_string_is_empty_success(self):
        result = self.toolbox("flight_search", "There is no flight from A to B on D.").execute(
            "flight_search", {"origin": "A", "destination": "B", "departure_date": "D"})
        self.assertTrue(result["ok"])
        self.assertTrue(result["empty"])

    def test_dataframe_keeps_row_order_and_fields(self):
        frame = pd.DataFrame([{"Name": "Second", "Cost": 2}, {"Name": "First", "Cost": 1}])
        result = self.toolbox("restaurant_search", frame).execute("restaurant_search", {"city": "B"})
        self.assertEqual(result["count"], 2)
        self.assertEqual([row["Name"] for row in result["data"]], ["Second", "First"])
        self.assertEqual(set(result["data"][0]), {"Name", "Cost"})


if __name__ == "__main__":
    unittest.main()
