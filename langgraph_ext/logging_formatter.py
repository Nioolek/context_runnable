"""
日志 Formatter - 从 ContextVar 获取上下文信息

提供:
- ContextFormatter: 自动从 ContextVar 获取 session_id/user_id/trace_id
- setup_logging(): 快速设置日志格式
"""

import logging
import sys
from typing import Optional


from .context_vars import get_session_id, get_user_id, get_trace_id


class ContextFormatter(logging.Formatter):
    """从 ContextVar 获取上下文的日志 Formatter
    
    默认格式: [session_id][user_id] timestamp level name: message
    
    自定义格式示例：
        formatter = ContextFormatter(
            fmt="[%(session_id)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    """
    
    # 默认格式
    DEFAULT_FMT = "[%(session_id)s][%(user_id)s] %(asctime)s %(levelname)s %(name)s: %(message)s"
    DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"
    
    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
        include_trace_id: bool = False,
    ):
        """
        Args:
            fmt: 自定义格式字符串，默认使用 DEFAULT_FMT
            datefmt: 日期格式，默认使用 DEFAULT_DATEFMT
            include_trace_id: 是否包含 trace_id，默认 False
        """
        if fmt is None:
            if include_trace_id:
                fmt = "[%(session_id)s][%(user_id)s][%(trace_id)s] %(asctime)s %(levelname)s %(name)s: %(message)s"
            else:
                fmt = self.DEFAULT_FMT
        
        if datefmt is None:
            datefmt = self.DEFAULT_DATEFMT
        
        super().__init__(fmt=fmt, datefmt=datefmt)
        self._include_trace_id = include_trace_id
    
    def format(self, record: logging.LogRecord) -> str:
        """格式化日志记录，从 ContextVar 获取上下文"""
        # 获取上下文信息
        record.session_id = get_session_id() or "unknown"
        record.user_id = get_user_id() or "unknown"
        
        if self._include_trace_id:
            record.trace_id = get_trace_id() or "unknown"
        
        return super().format(record)


class ContextFilter(logging.Filter):
    """日志 Filter，从 ContextVar 获取上下文并添加到 record"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        record.session_id = get_session_id() or "unknown"
        record.user_id = get_user_id() or "unknown"
        record.trace_id = get_trace_id() or "unknown"
        return True


def setup_logging(
    level: int = logging.INFO,
    fmt: Optional[str] = None,
    datefmt: Optional[str] = None,
    include_trace_id: bool = False,
    handler: Optional[logging.Handler] = None,
    logger: Optional[logging.Logger] = None,
) -> logging.Logger:
    """快速设置日志
    
    Args:
        level: 日志级别，默认 INFO
        fmt: 自定义格式字符串
        datefmt: 日期格式
        include_trace_id: 是否包含 trace_id
        handler: 自定义 Handler，默认使用 StreamHandler
        logger: 要配置的 Logger，默认使用 root logger
    
    Returns:
        配置好的 Logger
    
    示例：
        # 简单使用
        setup_logging()
        
        # 自定义格式
        setup_logging(
            fmt="[%(session_id)s] %(message)s",
            level=logging.DEBUG
        )
        
        # 配置特定 logger
        logger = setup_logging(logger=logging.getLogger("myapp"))
    """
    formatter = ContextFormatter(
        fmt=fmt,
        datefmt=datefmt,
        include_trace_id=include_trace_id,
    )
    
    if handler is None:
        handler = logging.StreamHandler(sys.stderr)
    
    handler.setFormatter(formatter)
    
    if logger is None:
        logger = logging.root
    
    # 清除现有 handlers
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    
    return logger


def add_context_to_existing_logger(logger: logging.Logger) -> None:
    """为现有 logger 添加 ContextFilter（不改变格式）
    
    Args:
        logger: 要添加 Filter 的 Logger
    
    示例：
        logger = logging.getLogger("myapp")
        add_context_to_existing_logger(logger)
        # 现在 record.session_id, record.user_id 可用
    """
    context_filter = ContextFilter()
    logger.addFilter(context_filter)