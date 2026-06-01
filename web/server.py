"""
XNBot WebUI 后端
可独立运行（端口 8081），也可挂载到 bot 的 FastAPI 上（/web/ 路径）

独立启动：
  python web/server.py

挂载到 bot：
  bot.py 中自动挂载，访问 http://host:8080/web/
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="XNBot WebUI", version="1.0.0")

# 创建 API 子应用，挂载在 /web/api 下
api_app = FastAPI(title="XNBot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================
# 数据模型
# ========================

class ConfigUpdateRequest(BaseModel):
    content: str  # TOML 文本内容


# ========================
# 概览 API
# ========================

@api_app.get("/stats")
def get_stats():
    """获取总体统计数据 + 系统信息 + token 消耗"""
    from src.XN_Memory import get_store
    import sqlite3, platform, psutil, datetime

    stats = {
        "memory_count": 0,
        "graph_entity_count": 0,
        "graph_relation_count": 0,
        "user_count": 0,
        "bot_name": "",
        "bot_status": "running",
        # 系统信息
        "sys": {},
        # token 统计
        "tokens": {},
    }

    # 记忆统计
    try:
        store = get_store()
        db_path = store.db_path
        conn = sqlite3.connect(str(db_path))
        cur = conn.execute("SELECT COUNT(*) FROM memories")
        stats["memory_count"] = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(DISTINCT user_id) FROM memories")
        stats["user_count"] = cur.fetchone()[0]
        conn.close()
    except Exception:
        pass

    # 图统计
    try:
        from src.XN_Memory import get_graph_store
        gs = get_graph_store()
        if gs._conn:
            r = gs._conn.execute("MATCH (e:Entity) RETURN COUNT(e) AS cnt")
            stats["graph_entity_count"] = int(r.get_as_df().iloc[0]["cnt"])
            r = gs._conn.execute("MATCH ()-[r:Relation]->() RETURN COUNT(r) AS cnt")
            stats["graph_relation_count"] = int(r.get_as_df().iloc[0]["cnt"])
    except Exception:
        pass

    # bot 名称
    try:
        from src.bot.core.config_loader import get_bot_config
        cfg = get_bot_config()
        stats["bot_name"] = cfg.get("bot", {}).get("name", "小雫")
    except Exception:
        pass

    # 系统信息
    try:
        cpu_percent = psutil.cpu_percent(interval=0.2)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        cpu_freq = psutil.cpu_freq()
        cpu_name = ""
        try:
            import subprocess
            if platform.system() == "Windows":
                result = subprocess.check_output(
                    "wmic cpu get Name /value", shell=True, text=True, timeout=3
                )
                for line in result.splitlines():
                    if "Name=" in line:
                        cpu_name = line.split("=", 1)[1].strip()
                        break
            else:
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if "model name" in line:
                            cpu_name = line.split(":", 1)[1].strip()
                            break
        except Exception:
            pass
        stats["sys"] = {
            "os": f"{platform.system()} {platform.release()}",
            "cpu_name": cpu_name,
            "cpu_percent": round(cpu_percent, 1),
            "cpu_cores": psutil.cpu_count(logical=False),
            "cpu_threads": psutil.cpu_count(logical=True),
            "cpu_freq_mhz": round(cpu_freq.current) if cpu_freq else None,
            "cpu_freq_max_mhz": round(cpu_freq.max) if cpu_freq and cpu_freq.max else None,
            "mem_total_gb": round(mem.total / 1024**3, 1),
            "mem_used_gb": round(mem.used / 1024**3, 1),
            "mem_percent": round(mem.percent, 1),
            "disk_total_gb": round(disk.total / 1024**3, 1),
            "disk_used_gb": round(disk.used / 1024**3, 1),
            "disk_percent": round(disk.percent, 1),
        }
    except Exception:
        pass

    # token 统计（从 LLM 日志解析）
    try:
        import re, json as _json
        log_path = ROOT / "data" / "logs" / "LLM_LOG.log"
        if log_path.exists():
            today = datetime.date.today().strftime("%Y-%m-%d")
            total_prompt = total_completion = 0
            today_prompt = today_completion = 0
            model_totals: dict = {}
            current_model = "unknown"
            is_today = False

            for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
                # 模型名: [2026-05-13 00:56:54] Model: xxx | Session: ...
                m = re.search(r'\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\s*Model:\s*([^\s|]+)', line)
                if m:
                    current_model = m.group(1)
                    is_today = line.lstrip("[").startswith(today)
                    continue
                # Usage JSON: Usage: {"prompt_tokens": N, "completion_tokens": N, ...}
                if line.startswith("Usage:"):
                    try:
                        usage = _json.loads(line[6:].strip())
                    except Exception:
                        continue
                    p = usage.get("prompt_tokens", 0)
                    c = usage.get("completion_tokens", 0)
                    total_prompt += p
                    total_completion += c
                    model_totals[current_model] = model_totals.get(current_model, {"prompt": 0, "completion": 0})
                    model_totals[current_model]["prompt"] += p
                    model_totals[current_model]["completion"] += c
                    if is_today:
                        today_prompt += p
                        today_completion += c

            stats["tokens"] = {
                "total_prompt": total_prompt,
                "total_completion": total_completion,
                "total_all": total_prompt + total_completion,
                "today_prompt": today_prompt,
                "today_completion": today_completion,
                "today_all": today_prompt + today_completion,
                "by_model": model_totals,
            }
    except Exception:
        pass

    return stats


# ========================
# 记忆 API
# ========================

@api_app.get("/memories")
def list_memories(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = None,
    keyword: Optional[str] = None,
):
    """分页获取记忆列表"""
    import sqlite3
    from src.XN_Memory import get_store

    store = get_store()
    conn = sqlite3.connect(str(store.db_path))
    conn.row_factory = sqlite3.Row

    conditions = []
    params: list = []

    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)
    if keyword:
        conditions.append("(user_text LIKE ? OR bot_text LIKE ? OR keywords LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    total = conn.execute(f"SELECT COUNT(*) FROM memories {where}", params).fetchone()[0]

    offset = (page - 1) * page_size
    rows = conn.execute(
        f"SELECT * FROM memories {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [page_size, offset],
    ).fetchall()

    conn.close()

    from datetime import datetime
    items = []
    for row in rows:
        d = dict(row)
        d["created_at_str"] = datetime.fromtimestamp(d["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
        items.append(d)

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@api_app.delete("/memories/{memory_id}")
def delete_memory(memory_id: int):
    """删除单条记忆"""
    import sqlite3
    from src.XN_Memory import get_store

    store = get_store()
    conn = sqlite3.connect(str(store.db_path))
    conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@api_app.get("/memories/users")
def list_users():
    """获取所有用户列表"""
    import sqlite3
    from src.XN_Memory import get_store

    store = get_store()
    conn = sqlite3.connect(str(store.db_path))
    rows = conn.execute(
        "SELECT user_id, nickname, COUNT(*) as count FROM memories GROUP BY user_id ORDER BY count DESC"
    ).fetchall()
    conn.close()
    return [{"user_id": r[0], "nickname": r[1], "count": r[2]} for r in rows]


# ========================
# 图谱 API
# ========================

@api_app.get("/graph/entities")
def list_entities(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = None,
    keyword: Optional[str] = None,
):
    """分页获取图实体列表"""
    from src.XN_Memory import get_graph_store

    gs = get_graph_store()
    if not gs._conn:
        return {"total": 0, "items": []}

    try:
        conn = gs._conn

        conditions = []
        params = {}

        if user_id:
            conditions.append("e.user_id = $uid")
            params["uid"] = user_id
        if keyword:
            conditions.append("(e.name CONTAINS $kw OR e.summary CONTAINS $kw)")
            params["kw"] = keyword

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        r_total = conn.execute(
            f"MATCH (e:Entity) {where} RETURN COUNT(e) AS cnt",
            params if params else None,
        )
        total = int(r_total.get_as_df().iloc[0]["cnt"])

        offset = (page - 1) * page_size
        r = conn.execute(
            f"MATCH (e:Entity) {where} RETURN e.id, e.name, e.entity_type, e.summary, e.user_id, e.created_at "
            f"ORDER BY e.created_at DESC SKIP {offset} LIMIT {page_size}",
            params if params else None,
        )
        df = r.get_as_df()
        from datetime import datetime
        items = []
        for _, row in df.iterrows():
            items.append({
                "id": int(row["e.id"]),
                "name": row["e.name"],
                "entity_type": row["e.entity_type"],
                "summary": row["e.summary"],
                "user_id": row["e.user_id"],
                "created_at": datetime.fromtimestamp(float(row["e.created_at"])).strftime("%Y-%m-%d %H:%M:%S"),
            })
        return {"total": total, "page": page, "page_size": page_size, "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@api_app.get("/graph/relations")
def list_relations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = None,
):
    """分页获取图关系列表"""
    from src.XN_Memory import get_graph_store

    gs = get_graph_store()
    if not gs._conn:
        return {"total": 0, "items": []}

    try:
        conn = gs._conn

        conditions = []
        params = {}
        if user_id:
            conditions.append("r.user_id = $uid")
            params["uid"] = user_id

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        r_total = conn.execute(
            f"MATCH (a:Entity)-[r:Relation]->(b:Entity) {where} RETURN COUNT(r) AS cnt",
            params if params else None,
        )
        total = int(r_total.get_as_df().iloc[0]["cnt"])

        offset = (page - 1) * page_size
        r = conn.execute(
            f"MATCH (a:Entity)-[r:Relation]->(b:Entity) {where} "
            f"RETURN a.name, b.name, r.rel_type, r.description, r.created_at "
            f"ORDER BY r.created_at DESC SKIP {offset} LIMIT {page_size}",
            params if params else None,
        )
        df = r.get_as_df()
        from datetime import datetime
        items = []
        for _, row in df.iterrows():
            items.append({
                "from": row["a.name"],
                "to": row["b.name"],
                "rel_type": row["r.rel_type"],
                "description": row["r.description"],
                "created_at": datetime.fromtimestamp(float(row["r.created_at"])).strftime("%Y-%m-%d %H:%M:%S"),
            })
        return {"total": total, "page": page, "page_size": page_size, "items": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# 配置 API
# ========================

CONFIG_FILES = {
    "bot": ROOT / "config" / "bot_config.toml",
    "ai": ROOT / "config" / "ai_config.toml",
    "rey": ROOT / "config" / "rey_config.toml",
    "reply": ROOT / "config" / "reply_config.toml",
    "emotion": ROOT / "config" / "emotion_config.toml",
    "emoji": ROOT / "config" / "emoji_config.toml",
}


@api_app.get("/config")
def list_configs():
    """获取所有配置文件名"""
    return {"configs": list(CONFIG_FILES.keys())}


@api_app.get("/config/{name}")
def get_config(name: str):
    """获取配置文件内容"""
    if name not in CONFIG_FILES:
        raise HTTPException(status_code=404, detail="配置文件不存在")
    path = CONFIG_FILES[name]
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    return {"name": name, "content": path.read_text(encoding="utf-8")}


@api_app.put("/config/{name}")
def update_config(name: str, body: ConfigUpdateRequest):
    """更新配置文件内容"""
    if name not in CONFIG_FILES:
        raise HTTPException(status_code=404, detail="配置文件不存在")
    path = CONFIG_FILES[name]
    # 备份
    backup = path.with_suffix(".toml.bak")
    if path.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(body.content, encoding="utf-8")
    return {"ok": True}


# ========================
# Setup 向导 API
# ========================

class SetupTestRequest(BaseModel):
    base_url: str
    api_key: str
    model: str

@api_app.post("/setup/test_connection")
async def setup_test_connection(req: SetupTestRequest):
    """测试 AI 服务连接"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{req.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {req.api_key}", "Content-Type": "application/json"},
                json={"model": req.model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
            )
            if resp.status_code == 200:
                return {"ok": True, "message": "连接成功"}
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


class SetupSaveRequest(BaseModel):
    ai: dict
    bot: dict

@api_app.post("/setup/save")
def setup_save(req: SetupSaveRequest):
    """保存向导配置到 TOML 文件"""
    import toml

    # 保存 ai_config.toml
    ai_path = ROOT / "config" / "ai_config.toml"
    ai_data = {}
    if ai_path.exists():
        ai_data = toml.loads(ai_path.read_text(encoding="utf-8"))

    # 更新 servers
    if "servers" not in ai_data:
        ai_data["servers"] = {}
    ai_data["servers"]["default"] = {
        "base_url": req.ai["base_url"],
        "api_key": req.ai["api_key"],
    }
    # 更新 models
    if "models" not in ai_data:
        ai_data["models"] = {}
    ai_data["models"]["default"] = {
        "name": req.ai["model"],
        "max_tokens": 2048,
    }
    if req.ai.get("embed_model"):
        ai_data["models"]["embed"] = {
            "name": req.ai["embed_model"],
            "max_tokens": 512,
        }

    ai_path.parent.mkdir(parents=True, exist_ok=True)
    ai_path.write_text(toml.dumps(ai_data), encoding="utf-8")

    # 保存 bot_config.toml
    bot_path = ROOT / "config" / "bot_config.toml"
    bot_data = {}
    if bot_path.exists():
        bot_data = toml.loads(bot_path.read_text(encoding="utf-8"))
    bot_data["bot"] = {
        "name": req.bot["name"],
        "short_desc": req.bot.get("short_desc", ""),
    }
    if req.bot.get("onebot_url"):
        bot_data.setdefault("onebot", {})["url"] = req.bot["onebot_url"]

    bot_path.write_text(toml.dumps(bot_data), encoding="utf-8")

    return {"ok": True}


@api_app.get("/setup/status")
def setup_status():
    """检查是否已完成初始化配置"""
    ai_path = ROOT / "config" / "ai_config.toml"
    if ai_path.exists():
        content = ai_path.read_text(encoding="utf-8")
        if "api_key" in content and "sk-" in content:
            return {"configured": True}
    return {"configured": False}


# ========================
# XN_Core API
# ========================

@api_app.get("/xn_core/reflections")
def list_reflections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = None,
):
    """分页获取反思日记"""
    import sqlite3
    from src.XN_Memory import get_store
    from datetime import datetime

    store = get_store()
    conn = sqlite3.connect(str(store.db_path))
    conn.row_factory = sqlite3.Row

    conditions = []
    params: list = []
    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    total = conn.execute(f"SELECT COUNT(*) FROM reflections {where}", params).fetchone()[0]
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"SELECT * FROM reflections {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [page_size, offset],
    ).fetchall()
    conn.close()

    items = []
    for row in rows:
        d = dict(row)
        d["created_at_str"] = datetime.fromtimestamp(d["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
        d["sleep_start_str"] = datetime.fromtimestamp(d["sleep_start"]).strftime("%H:%M")
        d["sleep_end_str"] = datetime.fromtimestamp(d["sleep_end"]).strftime("%H:%M")
        try:
            import json as _json
            hl = d.get("highlights") or "[]"
            d["highlights_list"] = _json.loads(hl) if isinstance(hl, str) else hl
        except Exception:
            d["highlights_list"] = []
        items.append(d)

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@api_app.get("/xn_core/heartbeat_logs")
def list_heartbeat_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[str] = None,
):
    """分页获取心跳日志"""
    import sqlite3
    from src.XN_Memory import get_store
    from datetime import datetime

    store = get_store()
    conn = sqlite3.connect(str(store.db_path))
    conn.row_factory = sqlite3.Row

    conditions = []
    params: list = []
    if user_id:
        conditions.append("user_id = ?")
        params.append(user_id)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    total = conn.execute(f"SELECT COUNT(*) FROM heartbeat_log {where}", params).fetchone()[0]
    offset = (page - 1) * page_size
    rows = conn.execute(
        f"SELECT * FROM heartbeat_log {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [page_size, offset],
    ).fetchall()
    conn.close()

    items = []
    for row in rows:
        d = dict(row)
        d["created_at_str"] = datetime.fromtimestamp(d["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
        d["trigger_time_str"] = datetime.fromtimestamp(d["trigger_time"]).strftime("%H:%M:%S")
        items.append(d)

    return {"total": total, "page": page, "page_size": page_size, "items": items}


@api_app.get("/xn_core/status")
def get_xn_core_status():
    """获取 XN_Core 当前状态"""
    import json
    from pathlib import Path
    from src.XN_Memory import get_store
    from datetime import datetime

    result = {
        "enabled": True,
        "sleeping_users": [],
        "reflections_count": 0,
        "heartbeat_count": 0,
    }

    # 读取配置
    try:
        from src.bot.core.config_loader import get_bot_config
        cfg = get_bot_config()
        xn_cfg = cfg.get("xn_core", {})
        result["enabled"] = xn_cfg.get("enabled", True)
        hb = xn_cfg.get("heartbeat", {})
        result["max_beats"] = hb.get("max_beats_per_day", 8)
        result["min_beats"] = hb.get("min_beats_per_day", 3)
        result["sleep_hours_range"] = [
            xn_cfg.get("sleep", {}).get("min_sleep_hours", 6),
            xn_cfg.get("sleep", {}).get("max_sleep_hours", 12),
        ]
    except Exception:
        pass

    # 读取反思和心跳数量
    try:
        store = get_store()
        import sqlite3
        conn = sqlite3.connect(str(store.db_path))
        conn.row_factory = sqlite3.Row
        result["reflections_count"] = conn.execute("SELECT COUNT(*) FROM reflections").fetchone()[0]
        result["heartbeat_count"] = conn.execute("SELECT COUNT(*) FROM heartbeat_log").fetchone()[0]
        # 最近一次反思
        row = conn.execute("SELECT * FROM reflections ORDER BY created_at DESC LIMIT 1").fetchone()
        if row:
            d = dict(row)
            result["last_reflection"] = {
                "user_id": d.get("user_id"),
                "summary": (d.get("summary") or "")[:100],
                "feeling": (d.get("feeling") or "")[:80],
                "health_score": d.get("health_score", 0),
                "created_at_str": datetime.fromtimestamp(d["created_at"]).strftime("%Y-%m-%d %H:%M"),
            }
        hb = store.count_heartbeat_today()
        result["heartbeat_today"] = hb
        conn.close()
    except Exception:
        pass

    try:
        from XN_Core.relation import get_relation
        for f in (ROOT / "data" / "core_state").glob("*_relation.json"):
            uid = f.stem.replace("_relation", "")
            result.setdefault("relations", {})[uid] = get_relation(uid)
    except Exception:
        pass

    try:
        from XN_Core.reflection import is_sleeping, get_sleep_state
        from src.XN_Memory import get_store
        store = get_store()
        for f in (ROOT / "data" / "core_state").glob("*_sleep.json"):
            uid = f.stem.replace("_sleep", "")
            if is_sleeping(uid):
                st = get_sleep_state(uid) or {}
                since = st.get("sleep_start", 0)
                result.setdefault("sleep_inbox", {})[uid] = store.count_sleep_period_user_messages(
                    uid, since,
                )
    except Exception:
        pass

    # 读取日程和心跳 JSON
    core_state_dir = ROOT / "data" / "core_state"
    if core_state_dir.exists():
        for f in core_state_dir.iterdir():
            if f.suffix == ".json":
                name = f.stem  # e.g. "123456_schedule"
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    result[name] = data
                except Exception:
                    pass

    # 读取睡眠状态（从 reflection 模块）
    try:
        from XN_Core.reflection import _sleep_state, _last_wake_time
        for uid, state in _sleep_state.items():
            if state.get("sleeping"):
                wake_str = datetime.fromtimestamp(state["wake_time"]).strftime("%H:%M") if state.get("wake_time") else "未知"
                result["sleeping_users"].append({
                    "user_id": uid,
                    "sleep_start": datetime.fromtimestamp(state["sleep_start"]).strftime("%H:%M") if state.get("sleep_start") else "未知",
                    "wake_time": wake_str,
                    "sleep_start_ts": state.get("sleep_start", 0),
                    "wake_time_ts": state.get("wake_time", 0),
                })
    except Exception:
        pass

    return result


# ========================
# 日志 API
# ========================

LOG_FILES = {
    "llm": ROOT / "data" / "logs" / "LLM_LOG.log",
    "agent": ROOT / "data" / "logs" / "AGENT_LOG.log",
}


@api_app.get("/logs/{name}")
def get_log(
    name: str,
    lines: int = Query(200, ge=1, le=2000),
    filter: Optional[str] = None,
):
    """获取日志文件最后 N 行"""
    if name not in LOG_FILES:
        raise HTTPException(status_code=404, detail="日志文件不存在")
    path = LOG_FILES[name]
    if not path.exists():
        return {"lines": []}

    all_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if filter:
        all_lines = [l for l in all_lines if filter.lower() in l.lower()]
    return {"lines": all_lines[-lines:]}


@api_app.get("/logs")
def list_logs():
    return {"logs": list(LOG_FILES.keys())}


# ========================
# 音频文件 API
# ========================

MUSIC_DIR = Path(__file__).parent / "music"


@api_app.get("/music/list")
def list_music():
    """扫描 web/music 目录的音频文件，返回列表"""
    import re
    audio_exts = {'.mp3', '.flac', '.wav', '.ogg', '.m4a', '.aac'}
    tracks = []
    if not MUSIC_DIR.exists():
        return {'tracks': []}
    for f in MUSIC_DIR.iterdir():
        if f.suffix.lower() in audio_exts and f.is_file():
            # 尝试从文件名解析 title / artist，格式：《title》-artist 或 title - artist
            name = f.stem
            m = re.match(r'[《【](.+?)[》】]\s*[-—]\s*(.+)', name)
            if m:
                title, artist = m.group(1).strip(), m.group(2).strip()
            elif ' - ' in name:
                parts = name.split(' - ', 1)
                title, artist = parts[0].strip(), parts[1].strip()
            elif '-' in name:
                parts = name.split('-', 1)
                title, artist = parts[0].strip(), parts[1].strip()
            else:
                title, artist = name, '未知'
            tracks.append({
                'title': title,
                'artist': artist,
                'filename': f.name,
            })
    return {'tracks': tracks}


@api_app.get("/music/file/{filename}")
def get_music_file(filename: str):
    """提供音频文件下载/流式播放"""
    from fastapi.responses import FileResponse
    # 防止路径穿越
    safe_name = Path(filename).name
    file_path = MUSIC_DIR / safe_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    audio_exts = {'.mp3', '.flac', '.wav', '.ogg', '.m4a', '.aac'}
    if file_path.suffix.lower() not in audio_exts:
        raise HTTPException(status_code=403, detail="不支持的文件类型")
    return FileResponse(
        str(file_path),
        media_type='audio/mpeg',
        headers={'Accept-Ranges': 'bytes'},
    )


# ========================
# 静态文件（生产环境）
# ========================

DIST_DIR = Path(__file__).parent / "frontend" / "dist"


# 挂载 API 子应用到 /web/api
app.mount("/web/api", api_app)


def _mount_static(sub_app: FastAPI):
    """挂载前端静态文件到子应用"""
    if DIST_DIR.exists():
        # 挂载 assets 目录
        sub_app.mount("/web/app/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")


_mount_static(app)


# 根路径重定向到 WebUI
@app.get("/")
async def root_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/web/app")


@app.get("/web")
async def web_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/web/app")


@app.get("/web/app/{full_path:path}")
async def web_spa(full_path: str):
    # 如果是 assets 文件，让 StaticFiles 处理（不会到这里）
    # 否则返回 index.html（SPA 路由）
    index = DIST_DIR / "index.html"
    return FileResponse(str(index))


@app.get("/web/app")
async def web_spa_root():
    index = DIST_DIR / "index.html"
    return FileResponse(str(index))


# ========================
# 挂载到 bot 的 FastAPI
# ========================

def include_web_routes(bot_app: FastAPI):
    """将 WebUI 挂载到 bot 的 FastAPI 上，路径为 /web"""
    bot_app.mount("/web", app)


# ========================
# 独立启动入口
# ========================

if __name__ == "__main__":
    # 独立运行时需要初始化配置
    from src.bot.core.config_loader import init_config
    init_config()
    import uvicorn
    uvicorn.run("web.server:app", host="0.0.0.0", port=8081, reload=True)
