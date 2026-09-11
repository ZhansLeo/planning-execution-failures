"""Read-only adapters around the six official TravelPlanner information tools."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {"type": "function", "function": {"name": "city_search", "description": "List available destination cities in a US state.", "parameters": {"type": "object", "properties": {"state": {"type": "string"}}, "required": ["state"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "flight_search", "description": "Find official flights for an exact route and YYYY-MM-DD date.", "parameters": {"type": "object", "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}, "departure_date": {"type": "string"}}, "required": ["origin", "destination", "departure_date"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "restaurant_search", "description": "List all official restaurants in a city.", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "attraction_search", "description": "List all official attractions in a city.", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "accommodation_search", "description": "List all official accommodations in a city, including price, occupancy, room type, house rules, and minimum nights.", "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "distance_matrix", "description": "Get official inter-city duration, distance, and estimated cost.", "parameters": {"type": "object", "properties": {"origin": {"type": "string"}, "destination": {"type": "string"}, "mode": {"type": "string", "enum": ["self-driving", "taxi"]}}, "required": ["origin", "destination", "mode"], "additionalProperties": False}}},
]


def tool_schema_hash() -> str:
    import hashlib
    return hashlib.sha256(json.dumps(TOOL_SCHEMAS, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _json_value(value: Any) -> Any:
    """Convert official pandas/numpy results without changing row order."""
    try:
        import pandas as pd
        if isinstance(value, pd.DataFrame):
            return json.loads(value.to_json(orient="records", force_ascii=False))
    except ImportError:
        pass
    if isinstance(value, Exception):
        return {"error": type(value).__name__, "message": str(value)}
    return value


class OfficialToolbox:
    def __init__(self, repo: Path) -> None:
        repo = repo.resolve()
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        flights = importlib.import_module("tools.flights.apis").Flights
        restaurants = importlib.import_module("tools.restaurants.apis").Restaurants
        attractions = importlib.import_module("tools.attractions.apis").Attractions
        accommodations = importlib.import_module("tools.accommodations.apis").Accommodations
        cities = importlib.import_module("tools.cities.apis").Cities
        matrix = importlib.import_module("tools.googleDistanceMatrix.apis").GoogleDistanceMatrix
        self._tools = {
            "flight_search": flights(str(repo / "database/flights/clean_Flights_2022.csv")),
            "restaurant_search": restaurants(str(repo / "database/restaurants/clean_restaurant_2022.csv")),
            "attraction_search": attractions(str(repo / "database/attractions/attractions.csv")),
            "accommodation_search": accommodations(str(repo / "database/accommodations/clean_accommodations_2022.csv")),
            "city_search": cities(str(repo / "database/background/citySet_with_states.txt")),
        }
        distance = matrix.__new__(matrix)
        import pandas as pd
        distance.gplaces_api_key = ""
        distance.data = pd.read_csv(repo / "database/googleDistanceMatrix/distance.csv")
        self._tools["distance_matrix"] = distance

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            return {"ok": False, "error_type": "UnknownTool", "error": f"Unknown tool: {name}"}
        try:
            if name == "city_search":
                result = self._tools[name].run(arguments["state"])
            elif name == "flight_search":
                result = self._tools[name].run(arguments["origin"], arguments["destination"], arguments["departure_date"])
            elif name in {"restaurant_search", "attraction_search", "accommodation_search"}:
                result = self._tools[name].run(arguments["city"])
            else:
                result = self._tools[name].run(arguments["origin"], arguments["destination"], arguments["mode"])
            if isinstance(result, Exception):
                return {"ok": False, "error_type": type(result).__name__, "error": str(result)}
            value = _json_value(result)
            empty = ((isinstance(value, list) and not value) or
                     (isinstance(value, str) and any(marker in value.casefold() for marker in
                      ("there is no", "no valid information"))))
            return {"ok": True, "empty": empty, "count": len(value) if isinstance(value, list) else None, "data": value}
        except Exception as exc:
            return {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
