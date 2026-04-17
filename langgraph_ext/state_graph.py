"""
ContextAwareStateGraph - 自动包装节点的 StateGraph

继承 StateGraph，在 add_node 时自动使用 ContextAwareRunnableCallable 包装函数。
"""

from typing import Callable, Any, Optional

from langgraph.graph import StateGraph
from langgraph._internal._runnable import RunnableCallable

from .runnable import ContextAwareRunnableCallable


class ContextAwareStateGraph(StateGraph):
    """自动使用 ContextAwareRunnableCallable 的 StateGraph
    
    所有通过 add_node 添加的函数节点都会自动包装，
    实现上下文自动注入。
    
    使用方式：
        builder = ContextAwareStateGraph(State)
        builder.add_node("analyze", analyze_func)  # 自动包装
        builder.add_node("process", process_func)  # 自动包装
        graph = builder.compile(checkpointer=checkpointer)
    
    或者自定义上下文字段：
        builder = ContextAwareStateGraph(
            State,
            default_context_fields={"session_id": "session_id", "request_id": "trace_id"}
        )
        builder.add_node("analyze", analyze_func)  # 使用自定义映射
    """
    
    def __init__(
        self,
        state_schema: type,
        *,
        default_context_fields: Optional[dict[str, str]] = None,
        **kwargs,
    ):
        """
        Args:
            state_schema: State 类型
            default_context_fields: 默认上下文字段映射，会应用到所有节点
            **kwargs: 其他 StateGraph 参数
        """
        super().__init__(state_schema, **kwargs)
        self._default_context_fields = default_context_fields
    
    def add_node(
        self,
        key: str,
        node: Callable[..., Any] | RunnableCallable,
        *,
        context_fields: Optional[dict[str, str]] = None,
        **kwargs,
    ) -> None:
        """添加节点，自动包装普通函数
        
        Args:
            key: 节点名称
            node: 节点函数或 RunnableCallable
            context_fields: 自定义上下文字段映射（覆盖默认值）
            **kwargs: 其他参数
        
        说明：
            - 如果 node 已经是 RunnableCallable，不会再次包装
            - 如果 node 是普通函数，会自动用 ContextAwareRunnableCallable 包装
            - 如果没有指定 context_fields，使用 default_context_fields
        """
        # 如果已经是 RunnableCallable，不重复包装
        if isinstance(node, RunnableCallable):
            super().add_node(key, node)
            return
        
        # 使用自定义或默认上下文字段
        fields = context_fields or self._default_context_fields
        
        # 包装为 ContextAwareRunnableCallable
        wrapped_node = ContextAwareRunnableCallable(
            func=node,
            name=key,
            context_fields=fields,
            **kwargs,
        )
        
        super().add_node(key, wrapped_node)
    
    def add_node_with_custom_context(
        self,
        key: str,
        node: Callable[..., Any],
        context_fields: dict[str, str],
    ) -> None:
        """添加节点并指定自定义上下文字段
        
        Args:
            key: 节点名称
            node: 节点函数
            context_fields: 上下文字段映射 {state_field: var_name}
        
        示例：
            builder.add_node_with_custom_context(
                "special_node",
                special_func,
                context_fields={"request_id": "trace_id", "tenant": "tenant_id"}
            )
        """
        self.add_node(key, node, context_fields=context_fields)


# ============================================================
# 工厂函数
# ============================================================

def create_context_aware_graph(
    state_schema: type,
    nodes: dict[str, Callable],
    edges: list[tuple[str, str]],
    entry_point: str = None,
    context_fields: Optional[dict[str, str]] = None,
    checkpointer=None,
) -> ContextAwareStateGraph:
    """快速创建带上下文注入的图
    
    Args:
        state_schema: State 类型
        nodes: {节点名: 节点函数} 字典
        edges: [(源节点, 目标节点)] 边列表
        entry_point: 入口节点（默认 START）
        context_fields: 上下文字段映射
        checkpointer: Checkpointer
    
    Returns:
        编译好的图
    
    示例：
        graph = create_context_aware_graph(
            State,
            nodes={"analyze": analyze_func, "process": process_func},
            edges=[("analyze", "process"), ("process", END)],
            checkpointer=InMemorySaver(),
        )
    """
    from langgraph.constants import START, END
    
    builder = ContextAwareStateGraph(
        state_schema,
        default_context_fields=context_fields,
    )
    
    # 添加节点
    for name, func in nodes.items():
        builder.add_node(name, func)
    
    # 设置入口
    if entry_point:
        builder.add_edge(START, entry_point)
    else:
        # 自动设置第一个节点为入口
        if nodes:
            builder.add_edge(START, list(nodes.keys())[0])
    
    # 添加边
    for src, dst in edges:
        builder.add_edge(src, dst)
    
    # 编译
    if checkpointer:
        return builder.compile(checkpointer=checkpointer)
    return builder.compile()