"""
完整示例：使用 langgraph-ext 实现自动上下文注入

演示：
1. 日志自动带 session_id, user_id
2. interrupt 恢复后仍然带上下文
3. 多节点流转
"""

import uuid
import logging
from typing_extensions import TypedDict, Optional

from langgraph.graph import START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt, Command

# 导入 langgraph-ext
from langgraph_ext import (
    ContextAwareStateGraph,
    setup_logging,
    get_session_id,
    get_user_id,
    get_all_context,
)


# ============================================================
# 设置日志
# ============================================================

setup_logging(level=logging.INFO)


# ============================================================
# State 定义
# ============================================================

class State(TypedDict):
    session_id: str
    user_id: str
    trace_id: str
    messages: list
    result: dict
    approved: Optional[bool]


# ============================================================
# 节点定义
# ============================================================

def analyze_node(state: State, config):
    """分析节点"""
    logging.info("开始分析")
    # 输出：[abc123][user001] 2024-01-01 10:00:00 INFO analyze: 开始分析
    
    # 可以在代码中获取上下文
    session_id = get_session_id()
    user_id = get_user_id()
    context = get_all_context()
    
    logging.info(f"上下文：{context}")
    # 输出：[abc123][user001] ... INFO analyze: 上下文：{'session_id': 'abc123', 'user_id': 'user001', 'trace_id': 'trace001'}
    
    # 业务逻辑
    result = {"analysis": "数据已分析", "confidence": 0.75}
    
    logging.info("分析完成")
    return {"result": result}


def process_node(state: State, config):
    """处理节点"""
    logging.info("开始处理")
    # 输出：[abc123][user001] ... INFO process: 开始处理
    
    messages = state["messages"] + ["数据已处理"]
    
    logging.info("处理完成")
    return {"messages": messages}


def review_node(state: State, config):
    """审批节点（带 interrupt）"""
    logging.info("需要审批")
    # 输出：[abc123][user001] ... INFO review: 需要审批
    
    confidence = state["result"].get("confidence", 0)
    
    if confidence < 0.9:
        answer = interrupt(f"置信度 {confidence} 较低，是否继续？")
        
        # 恢复后继续执行
        approved = answer.lower() in ["是", "yes", "ok", "好的"]
        logging.info(f"用户回复：{answer}，审批结果：{approved}")
        # 输出：[abc123][user001] ... INFO review: 用户回复：是，审批结果：True
        
        return {"approved": approved, "messages": state["messages"] + [f"审批：{answer}"]}
    
    logging.info("置信度足够高，自动通过")
    return {"approved": True}


def final_node(state: State, config):
    """最终节点"""
    approved = state.get("approved", False)
    
    if approved:
        logging.info("流程完成，结果已确认")
    else:
        logging.info("流程被拒绝")
    
    return {"messages": state["messages"] + ["流程结束"]}


# ============================================================
# 构建图
# ============================================================

def build_graph():
    """构建带上下文注入的图"""
    builder = ContextAwareStateGraph(State)
    
    # 添加节点（自动包装，上下文自动注入）
    builder.add_node("analyze", analyze_node)
    builder.add_node("process", process_node)
    builder.add_node("review", review_node)
    builder.add_node("final", final_node)
    
    # 添加边
    builder.add_edge(START, "analyze")
    builder.add_edge("analyze", "process")
    builder.add_edge("process", "review")
    builder.add_edge("review", "final")
    builder.add_edge("final", END)
    
    # 编译
    checkpointer = InMemorySaver()
    return builder.compile(checkpointer=checkpointer)


# ============================================================
# 执行示例
# ============================================================

def main():
    graph = build_graph()
    
    # 初始输入
    input_state = {
        "session_id": "abc123",
        "user_id": "user001",
        "trace_id": "trace001",
        "messages": [],
        "result": {},
        "approved": None,
    }
    
    config = {"configurable": {"thread_id": uuid.uuid4()}}
    
    print("=" * 60)
    print("第一次执行（会中断）")
    print("=" * 60)
    
    for chunk in graph.stream(input_state, config):
        print(chunk)
    
    print("\n" + "=" * 60)
    print("恢复执行")
    print("=" * 60)
    
    for chunk in graph.stream(Command(resume="是"), config):
        print(chunk)
    
    print("\n" + "=" * 60)
    print("最终结果")
    print("=" * 60)
    
    final_state = graph.get_state(config)
    print(final_state.values)


if __name__ == "__main__":
    main()