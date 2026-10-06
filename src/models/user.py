class User:
    def __init__(self, user_id: str, username: str, email: str):
        self.user_id = user_id
        self.username = username
        self.email = email

    @staticmethod
    def is_valid_email(email: str) -> bool:
        return "@" in email and "." in email

    @staticmethod
    def is_valid_password(password: str) -> bool:
        return len(password) >= 6