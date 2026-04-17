"""
ContextAwareRunnableCallable - 自动注入上下文的节点基类

继承 RunnableCallable，在执行节点函数前自动从 input/state 提取上下文
并设置到 ContextVar，执行完成后自动清理。
"""

import asyncio
import inspect
from collections.abc import Coroutine
from contextvars import copy_context
from typing import Any, Callable, Awaitable, Optional, Sequence, cast

from langchain_core.runnables import RunnableConfig, Runnable

try:
    from langchain_core.tracers.langchain import LangChainTracer
except ImportError:
    LangChainTracer = None

from langgraph._internal._runnable import RunnableCallable, ASYNCIO_ACCEPTS_CONTEXT
from langgraph._internal._config import (
    patch_config,
    ensure_config,
    get_callback_manager_for_config,
    get_async_callback_manager_for_config,
)
from langgraph._internal._constants import CONF, CONFIG_KEY_RUNTIME

from .context_vars import ContextVarsManager, _CONTEXT_VARS


class ContextAwareRunnableCallable(RunnableCallable):
    """自动注入上下文的节点基类
    
    从 input/state 中提取指定字段（如 session_id、user_id），
    自动设置到 ContextVar，让 Logger Formatter 能够获取。
    
    使用方式：
        # 方式 1：直接创建
        node = ContextAwareRunnableCallable(my_func, name="my_node")
        
        # 方式 2：自定义上下文字段映射
        node = ContextAwareRunnableCallable(
            my_func,
            context_fields={"session_id": "session_id", "request_id": "trace_id"}
        )
        
        # 方式 3：使用 ContextAwareStateGraph.add_node() 自动包装
        builder = ContextAwareStateGraph(State)
        builder.add_node("analyze", my_func)  # 自动包装
    
    """
    
    # 默认：从 state 字段名 → ContextVar 名 的映射
    DEFAULT_CONTEXT_FIELDS: dict[str, str] = {
        "session_id": "session_id",
        "user_id": "user_id",
        "trace_id": "trace_id",
    }
    
    def __init__(
        self,
        func: Callable[..., Any] | None = None,
        afunc: Callable[..., Awaitable[Any]] | None = None,
        *,
        name: str | None = None,
        tags: Sequence[str] | None = None,
        trace: bool = True,
        recurse: bool = True,
        explode_args: bool = False,
        context_fields: dict[str, str] | None = None,
        **kwargs,
    ):
        """
        Args:
            func: 同步节点函数
            afunc: 异步节点函数
            name: 节点名称
            tags: Runnable tags
            trace: 是否启用 tracing
            recurse: 是否递归处理 Runnable 返回值
            explode_args: 是否展开 args
            context_fields: 自定义上下文字段映射 {state_field: context_var_name}
                           默认使用 DEFAULT_CONTEXT_FIELDS
        """
        super().__init__(
            func=func,
            afunc=afunc,
            name=name,
            tags=tags,
            trace=trace,
            recurse=recurse,
            explode_args=explode_args,
            **kwargs,
        )
        
        self._context_fields = context_fields or self.DEFAULT_CONTEXT_FIELDS.copy()
    
    def _extract_context_from_input(self, input: Any) -> dict[str, Any]:
        """从 input/state 中提取上下文值
        
        Args:
            input: 节点输入（通常是 State dict）
        
        Returns:
            {context_var_name: value} 字典
        """
        context_values = {}
        
        if isinstance(input, dict):
            for state_field, var_name in self._context_fields.items():
                if state_field in input:
                    value = input[state_field]
                    if value is not None:
                        context_values[var_name] = value
        
        return context_values
    
    def _get_kw_value(
        self,
        kw: str,
        runtime_key: str,
        default: Any,
        config: RunnableConfig,
        runtime: Any,
    ) -> Any:
        """获取 kw 参数值（继承自 RunnableCallable 的逻辑）
        
        Args:
            kw: 参数名（如 "config", "runtime", "writer"）
            runtime_key: runtime 中的属性名
            default: 默认值
            config: RunnableConfig
            runtime: Runtime 实例
        
        Returns:
            参数值
        """
        from langgraph._internal._typing import MISSING
        
        kw_value = MISSING
        
        if kw == "config":
            kw_value = config
        elif runtime is not None:
            if kw == "runtime":
                kw_value = runtime
            else:
                try:
                    kw_value = getattr(runtime, runtime_key)
                except AttributeError:
                    pass
        
        if kw_value is MISSING:
            if default is inspect.Parameter.empty:
                raise ValueError(
                    f"Missing required config key '{runtime_key}' for '{self.name}'."
                )
            kw_value = default
        
        return kw_value
    
    def invoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs,
    ) -> Any:
        """同步执行节点
        
        在执行前从 input 提取上下文并设置到 ContextVar，
        执行后自动清理。
        """
        if config is None:
            config = ensure_config()
        
        # 处理参数（继承父类逻辑）
        if self.explode_args:
            args, _kwargs = input
            kwargs = {**self.kwargs, **_kwargs, **kwargs}
        else:
            args = (input,)
            kwargs = {**self.kwargs, **kwargs}
        
        # 处理 runtime 注入（继承父类逻辑）
        runtime = config.get(CONF, {}).get(CONFIG_KEY_RUNTIME)
        
        for kw, (runtime_key, default) in self.func_accepts.items():
            if kw in kwargs:
                continue
            kw_value = self._get_kw_value(kw, runtime_key, default, config, runtime)
            if kw_value is not inspect.Parameter.empty:
                kwargs[kw] = kw_value
        
        # ════════════════════════════════════════════════════════════════
        # 关键步骤：提取上下文并设置 ContextVar
        # ════════════════════════════════════════════════════════════════
        context_values = self._extract_context_from_input(input)
        context_manager = ContextVarsManager()
        context_manager.set_multiple(context_values)
        
        try:
            if self.trace:
                # trace 模式：使用 callback manager
                callback_manager = get_callback_manager_for_config(config, self.tags)
                run_manager = callback_manager.on_chain_start(
                    None,
                    input,
                    name=config.get("run_name") or self.name,
                    run_id=config.pop("run_id", None),
                )
                
                try:
                    child_config = patch_config(
                        config, callbacks=run_manager.get_child()
                    )
                    
                    # 获取 run（用于 tracing）
                    run = None
                    if LangChainTracer is not None:
                        for h in run_manager.handlers:
                            if isinstance(h, LangChainTracer):
                                run = h.run_map.get(str(run_manager.run_id))
                                break
                    
                    # ══════════════════════════════════════════════════════
                    # 复制 context，在复制的 context 中设置 ContextVar
                    # ══════════════════════════════════════════════════════
                    ctx = copy_context()
                    for var_name, value in context_values.items():
                        var = _CONTEXT_VARS.get(var_name)
                        if var is not None:
                            ctx.run(var.set, value)
                    
                    # 执行节点函数
                    ret = ctx.run(self.func, *args, **kwargs)
                    
                except BaseException as e:
                    run_manager.on_chain_error(e)
                    raise
                else:
                    run_manager.on_chain_end(ret)
            else:
                # 非 trace 模式：直接执行（ContextVar 已在上面设置）
                ret = self.func(*args, **kwargs)
            
            # 处理 Runnable 返回值
            if self.recurse and isinstance(ret, Runnable):
                return ret.invoke(input, config)
            
            return ret
        
        finally:
            # ════════════════════════════════════════════════════════════════
            # 清理 ContextVar
            # ════════════════════════════════════════════════════════════════
            context_manager.reset_all()
    
    async def ainvoke(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs,
    ) -> Any:
        """异步执行节点
        
        在执行前从 input 提取上下文并设置到 ContextVar，
        执行后自动清理。
        """
        if not self.afunc:
            # 没有 async 函数，fallback 到 sync
            return self.invoke(input, config)
        
        if config is None:
            config = ensure_config()
        
        # 处理参数
        if self.explode_args:
            args, _kwargs = input
            kwargs = {**self.kwargs, **_kwargs, **kwargs}
        else:
            args = (input,)
            kwargs = {**self.kwargs, **kwargs}
        
        # 处理 runtime 注入
        runtime = config.get(CONF, {}).get(CONFIG_KEY_RUNTIME)
        
        for kw, (runtime_key, default) in self.func_accepts.items():
            if kw in kwargs:
                continue
            kw_value = self._get_kw_value(kw, runtime_key, default, config, runtime)
            if kw_value is not inspect.Parameter.empty:
                kwargs[kw] = kw_value
        
        # ════════════════════════════════════════════════════════════════
        # 提取上下文并设置 ContextVar
        # ════════════════════════════════════════════════════════════════
        context_values = self._extract_context_from_input(input)
        context_manager = ContextVarsManager()
        context_manager.set_multiple(context_values)
        
        try:
            if self.trace:
                # trace 模式
                callback_manager = get_async_callback_manager_for_config(config, self.tags)
                run_manager = await callback_manager.on_chain_start(
                    None,
                    input,
                    name=config.get("run_name") or self.name,
                    run_id=config.pop("run_id", None),
                )
                
                try:
                    child_config = patch_config(
                        config, callbacks=run_manager.get_child()
                    )
                    coro = cast(Coroutine, self.afunc(*args, **kwargs))
                    
                    # 获取 run
                    run = None
                    if LangChainTracer is not None:
                        for h in run_manager.handlers:
                            if isinstance(h, LangChainTracer):
                                run = h.run_map.get(str(run_manager.run_id))
                                break
                    
                    # ══════════════════════════════════════════════════════
                    # Python 3.11+ 支持 asyncio.create_task(context=...)
                    # ══════════════════════════════════════════════════════
                    if ASYNCIO_ACCEPTS_CONTEXT:
                        ctx = copy_context()
                        for var_name, value in context_values.items():
                            var = _CONTEXT_VARS.get(var_name)
                            if var is not None:
                                ctx.run(var.set, value)
                        
                        # 在 context 中执行 async 函数
                        ret = await asyncio.create_task(coro, context=ctx)
                    else:
                        # Python < 3.11: 直接执行（ContextVar 已在上面设置）
                        ret = await coro
                    
                except BaseException as e:
                    await run_manager.on_chain_error(e)
                    raise
                else:
                    await run_manager.on_chain_end(ret)
            else:
                # 非 trace 模式
                ret = await self.afunc(*args, **kwargs)
            
            # 处理 Runnable 返回值
            if self.recurse and isinstance(ret, Runnable):
                return await ret.ainvoke(input, config)
            
            return ret
        
        finally:
            # ════════════════════════════════════════════════════════════════
            # 清理 ContextVar
            # ════════════════════════════════════════════════════════════════
            context_manager.reset_all()


# ============================================================
# 工厂函数
# ============================================================

def create_context_aware_node(
    func: Callable[..., Any],
    name: Optional[str] = None,
    context_fields: Optional[dict[str, str]] = None,
    **kwargs,
) -> ContextAwareRunnableCallable:
    """创建自动注入上下文的节点
    
    Args:
        func: 节点函数
        name: 节点名称，默认使用 func.__name__
        context_fields: 自定义上下文字段映射
        **kwargs: 其他 RunnableCallable 参数
    
    Returns:
        ContextAwareRunnableCallable 实例
    
    示例：
        node = create_context_aware_node(my_func)
        node = create_context_aware_node(my_func, context_fields={"request_id": "trace_id"})
    """
    return ContextAwareRunnableCallable(
        func=func,
        name=name or func.__name__,
        context_fields=context_fields,
        **kwargs,
    )