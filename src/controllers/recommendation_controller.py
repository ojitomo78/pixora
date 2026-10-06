from typing import Any

from src.models.recommendation import PhotoSessionType, PhotoSpot
from src.services.api_client import ApiClient


class RecommendationController:
    def __init__(self, api_client: ApiClient | None = None):
        self.api_client = api_client or ApiClient()

    def recommend_poses(self, session_type: str) -> str:
        return self.recommend_pose_results(session_type)["recommendation"]

    def recommend_pose_results(self, session_type: str) -> dict[str, Any]:
        result = self.api_client.request(
            "POST", "/ai/poses", json={"session_type": session_type}
        )
        return result

    def get_spots(self, city: str | None = None) -> list[PhotoSpot]:
        params = {"city": city} if city else None
        spots = self.api_client.request("GET", "/spots", params=params)
        return [PhotoSpot(**spot) for spot in spots]

    def get_session_types(self) -> list[PhotoSessionType]:
        session_types = self.api_client.request("GET", "/session-types")
        return [PhotoSessionType(**item) for item in session_types]

    def recommend_spots(self, city: str, photo_type: str) -> str:
        return self.recommend_spot_results(city, photo_type)["recommendation"]

    def recommend_spot_results(self, city: str, photo_type: str) -> dict[str, Any]:
        result = self.api_client.request(
            "POST",
            "/ai/spots",
            json={"city": city, "photo_type": photo_type},
        )
        return result

    def ask_ai(self, prompt: str) -> list[dict[str, str]]:
        return self.ask_ai_result(prompt)["cards"]

    def ask_ai_result(self, prompt: str) -> dict[str, Any]:
        return self.api_client.request(
            "POST", "/ai/ask", json={"prompt": prompt}
        )
