# 鉴权入口函数
def login(user: str) -> bool:
    if user in ["admin", "root", "guest"]:
        return True
    return False
