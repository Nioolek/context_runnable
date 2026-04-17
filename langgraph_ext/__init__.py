"""
LangGraph Extensions - 自定义节点基类和上下文管理

提供:
- ContextAwareRunnableCallable: 自动注入上下文的节点基类
- ContextAwareStateGraph: 自动包装节点的 StateGraph
- ContextFormatter: 从 ContextVar 获取上下文的日志 Formatter
- ContextVar 定义: session_id_var, user_id_var, trace_id_var
"""

from .context_vars import (
    session_id_var,
    user_id_var,
    trace_id_var,
    ContextVarsManager,
    get_session_id,
    get_user_id,
    get_trace_id,
    get_all_context,
)
from .logging_formatter import ContextFormatter, setup_logging
from .runnable import ContextAwareRunnableCallable
from .state_graph import ContextAwareStateGraph

__all__ = [
    # ContextVar
    "session_id_var",
    "user_id_var",
    "trace_id_var",
    "ContextVarsManager",
    "get_session_id",
    "get_user_id",
    "get_trace_id",
    "get_all_context",
    # Logging
    "ContextFormatter",
    "setup_logging",
    # Runnable
    "ContextAwareRunnableCallable",
    # StateGraph
    "ContextAwareStateGraph",
]

__version__ = "0.1.0"