"""
测试 auth.py 中的登录逻辑
"""
import subprocess
import sys
import os

def login(user: str, password: str) -> bool:
    """调用 auth.py 中的 login 函数"""
    # 直接导入 auth 模块
    import importlib.util
    spec = importlib.util.spec_from_file_location("auth", "auth.py")
    auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(auth)
    
    return auth.login(user, password)

def test_cases():
    """测试用例"""
    test_cases = [
        # (用户名, 密码, 预期结果)
        ("admin", "admin123", True),   # 正确的用户名和密码
        ("admin", "wrongpass", False), # 错误的密码
        ("root", "root123", True),     # 正确的用户名和密码
        ("root", "wrongpass", False),  # 错误的密码
        ("guest", "guest123", True),   # 正确的用户名和密码
        ("guest", "wrongpass", False), # 错误的密码
        ("user1", "user123", False),   # 不存在的用户
        ("", "", False),               # 空用户名
        ("unknown", "pass", False)     # 未知用户
    ]
    
    print("开始测试登录逻辑...")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for user, password, expected in test_cases:
        result = login(user, password)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        
        print(f"{status}: login('{user}', '{password}') = {result} (expected {expected})")
        
        if result == expected:
            passed += 1
        else:
            failed += 1
    
    print("=" * 60)
    
    if failed == 0:
        print("🎉 所有测试用例通过！")
    else:
        print(f"💥 存在 {failed} 个失败的测试用例！")
    
    return failed == 0

if __name__ == "__main__":
    test_cases()