"""
ContextVar 定义和管理

定义用于存储上下文信息的 ContextVar:
- session_id: 会话 ID
- user_id: 用户 ID
- trace_id: 追踪 ID
"""

from contextvars import ContextVar, Token
from typing import Any, Optional


# ============================================================
# ContextVar 定义
# ============================================================

session_id_var: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)

# 注册表：var_name -> ContextVar
_CONTEXT_VARS: dict[str, ContextVar] = {
    "session_id": session_id_var,
    "user_id": user_id_var,
    "trace_id": trace_id_var,
}


# ============================================================
# ContextVar 管理器
# ============================================================

class ContextVarsManager:
    """管理多个 ContextVar 的设置和清理
    
    使用方式：
        manager = ContextVarsManager()
        manager.set("session_id", "abc123")
        manager.set("user_id", "user001")
        # ... 执行代码 ...
        manager.reset_all()  # 清理
    """
    
    def __init__(self):
        self._tokens: dict[str, Token] = {}
    
    def set(self, var_name: str, value: Any) -> Optional[Token]:
        """设置 ContextVar
        
        Args:
            var_name: ContextVar 名称（如 "session_id"）
            value: 要设置的值
        
        Returns:
            Token 用于后续重置，如果 var_name 不存在则返回 None
        """
        var = _CONTEXT_VARS.get(var_name)
        if var is None:
            return None
        
        if value is not None:
            token = var.set(value)
            self._tokens[var_name] = token
            return token
        return None
    
    def set_multiple(self, values: dict[str, Any]) -> None:
        """批量设置多个 ContextVar
        
        Args:
            values: {var_name: value} 字典
        """
        for var_name, value in values.items():
            self.set(var_name, value)
    
    def reset_all(self) -> None:
        """重置所有已设置的 ContextVar"""
        for var_name, token in self._tokens.items():
            var = _CONTEXT_VARS.get(var_name)
            if var is not None:
                try:
                    var.reset(token)
                except ValueError:
                    # Token 可能已经无效，忽略
                    pass
        self._tokens.clear()
    
    def get_token(self, var_name: str) -> Optional[Token]:
        """获取指定 ContextVar 的 token"""
        return self._tokens.get(var_name)


# ============================================================
# 辅助函数
# ============================================================

def get_session_id() -> Optional[str]:
    """获取当前 session_id"""
    return session_id_var.get()


def get_user_id() -> Optional[str]:
    """获取当前 user_id"""
    return user_id_var.get()


def get_trace_id() -> Optional[str]:
    """获取当前 trace_id"""
    return trace_id_var.get()


def get_all_context() -> dict[str, Optional[str]]:
    """获取所有上下文信息"""
    return {
        "session_id": get_session_id(),
        "user_id": get_user_id(),
        "trace_id": get_trace_id(),
    }


def register_context_var(name: str, var: ContextVar) -> None:
    """注册新的 ContextVar
    
    Args:
        name: ContextVar 名称
        var: ContextVar 实例
    """
    _CONTEXT_VARS[name] = var
    globals()[f"{name}_var"] = var


def get_context_var(name: str) -> Optional[ContextVar]:
    """获取注册的 ContextVar
    
    Args:
        name: ContextVar 名称
    
    Returns:
        ContextVar 实例，如果不存在返回 None
    """
    return _CONTEXT_VARS.get(name)