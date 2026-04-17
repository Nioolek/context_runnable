# LangGraph Extensions

自动注入上下文的 LangGraph 节点基类和 StateGraph 扩展。

## 功能

- **ContextAwareRunnableCallable**: 自动从 State 提取上下文并设置到 ContextVar
- **ContextAwareStateGraph**: 自动包装节点函数的 StateGraph
- **ContextFormatter**: 从 ContextVar 获取上下文的日志 Formatter
- **ContextVar 管理**: session_id, user_id, trace_id

## 安装

```bash
pip install langgraph-ext
```

或从源码安装：

```bash
cd langgraph-ext
pip install -e .
```

## 快速使用

### 1. 设置日志

```python
from langgraph_ext import setup_logging

# 自动从 ContextVar 获取 session_id, user_id
setup_logging()
# 输出格式：[session_id][user_id] timestamp level name: message
```

### 2. 创建图（自动注入上下文）

```python
from typing_extensions import TypedDict
from langgraph.graph import START, END
from langgraph.checkpoint.memory import InMemorySaver
from langgraph_ext import ContextAwareStateGraph

class State(TypedDict):
    session_id: str
    user_id: str
    messages: list

def analyze(state: State, config):
    import logging
    logging.info("分析开始")  # 自动带 session_id, user_id
    return {"messages": ["analyzed"]}

def process(state: State, config):
    import logging
    logging.info("处理开始")  # 自动带 session_id, user_id
    return {"messages": state["messages"] + ["processed"]}

# 创建图（自动包装节点）
builder = ContextAwareStateGraph(State)
builder.add_node("analyze", analyze)
builder.add_node("process", process)
builder.add_edge(START, "analyze")
builder.add_edge("analyze", "process")
builder.add_edge("process", END)

graph = builder.compile(checkpointer=InMemorySaver())
```

### 3. 执行

```python
import uuid

result = graph.invoke({
    "session_id": "abc123",
    "user_id": "user001",
    "messages": [],
}, config={"configurable": {"thread_id": uuid.uuid4()}})

# 日志输出：
# [abc123][user001] 2024-01-01 10:00:00 INFO analyze: 分析开始
# [abc123][user001] 2024-01-01 10:00:01 INFO process: 处理开始
```

### 4. 支持 interrupt（恢复时自动重新注入）

```python
from langgraph.types import interrupt

def review(state: State, config):
    import logging
    logging.info("需要审批")
    
    answer = interrupt("确认继续？")
    
    logging.info(f"用户回复：{answer}")  # 恢复后仍然带 session_id, user_id
    return {"messages": state["messages"] + [answer]}

# 第一次执行（中断）
for chunk in graph.stream(input, config):
    print(chunk)

# 恢复执行
from langgraph.types import Command
for chunk in graph.stream(Command(resume="是"), config):
    print(chunk)
```

## 自定义上下文字段

```python
# 方式 1：自定义 StateGraph 默认字段
builder = ContextAwareStateGraph(
    State,
    default_context_fields={"session_id": "session_id", "request_id": "trace_id"}
)

# 方式 2：为单个节点自定义
builder.add_node("special", special_func, context_fields={"tenant": "tenant_id"})
```

## 在节点中获取上下文

```python
from langgraph_ext import get_session_id, get_user_id, get_all_context

def my_node(state: State, config):
    session_id = get_session_id()  # 从 ContextVar 获取
    user_id = get_user_id()
    context = get_all_context()  # {"session_id": ..., "user_id": ..., "trace_id": ...}
    
    print(f"Session: {session_id}, User: {user_id}")
    return {}
```

## 文件结构

```
langgraph-ext/
├── langgraph_ext/
│   ├── __init__.py          # 导出所有模块
│   ├── context_vars.py      # ContextVar 定义和管理
│   ├── logging_formatter.py # 日志 Formatter
│   ├── runnable.py          # ContextAwareRunnableCallable
│   └── state_graph.py       # ContextAwareStateGraph
├── pyproject.toml
└── README.md
```

## License

MIT