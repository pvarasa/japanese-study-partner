from fastapi import Header


def get_user_id(x_user_id: str = Header(default="default")) -> str:
    return x_user_id
