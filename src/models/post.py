class Post:
    def __init__(
        self,
        post_id: str,
        author: str,
        image_data: bytes,
        caption: str,
        description: str = "",
        location: str | None = None,
        pose_utilizada: str | None = None,
        author_id: str = "",
        likes_count: int = 0,
        liked_by_me: bool = False,
    ):
        self.post_id = post_id
        self.author = author
        self.author_id = author_id
        self.image_data = image_data
        self.caption = caption
        self.description = description
        self.location = location
        self.pose_utilizada = pose_utilizada
        self.likes_count = likes_count
        self.liked_by_me = liked_by_me