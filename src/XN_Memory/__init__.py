"""
XN_Memory - 记忆核心模块
负责记忆的存储、写入和管理
检索侧由 Agent 工具负责
"""
from src.XN_Memory.store import MemoryStore
from src.XN_Memory.writer import MemoryWriter
from src.XN_Memory.faiss_manager import FaissManager
from src.XN_Memory.graph_store import GraphStore
from src.XN_Memory.graph_writer import GraphWriter, get_graph_writer

_store: MemoryStore | None = None
_writer: MemoryWriter | None = None
_graph_store: GraphStore | None = None
_faiss: FaissManager | None = None


def init_memory(db_path: str | None = None, index_dir: str | None = None, graph_dir: str | None = None) -> None:
    """初始化记忆系统（对话记忆 + 图记忆）"""
    global _store, _writer, _graph_store, _faiss
    _store = MemoryStore(db_path=db_path)
    _store.init_db()
    _faiss = FaissManager(index_dir=index_dir)
    _writer = MemoryWriter(store=_store, faiss=_faiss)

    _graph_store = GraphStore(graph_dir=graph_dir)
    get_graph_writer().set_graph_store(_graph_store)


def get_store() -> MemoryStore:
    if _store is None:
        raise RuntimeError("记忆系统未初始化，请先调用 init_memory()")
    return _store


def get_writer() -> MemoryWriter:
    if _writer is None:
        raise RuntimeError("记忆系统未初始化，请先调用 init_memory()")
    return _writer


def get_faiss() -> FaissManager:
    if _faiss is None:
        raise RuntimeError("记忆系统未初始化，请先调用 init_memory()")
    return _faiss


def get_graph_store() -> GraphStore:
    if _graph_store is None:
        raise RuntimeError("记忆系统未初始化，请先调用 init_memory()")
    return _graph_store
