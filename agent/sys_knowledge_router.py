import asyncio
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import insert, select, update, delete
from data_access.sys_db_conn import sys_engine
from data_access.base_knowledge_db import base_knowledge
from data_access.db_query_guide_db import db_query_guide
from data_access.code_guide_db import code_guide
from data_access.graph_code_guide_db import graph_code_guide
from data_access.think_guide_db import think_guide
from data_access.doc_guide_db import doc_guide
from data_access.brief_info_db import brief_info

router = APIRouter()


class KnowledgeEntry(BaseModel):
    key: str
    value: str


class KnowledgeUpdate(BaseModel):
    key: str | None = None
    value: str | None = None


# ---- base_knowledge CRUD ----

@router.get("/api/sys-knowledge/base-knowledge/")
async def list_base_knowledge():
    with sys_engine.connect() as conn:
        rows = conn.execute(select(base_knowledge).order_by(base_knowledge.c.id)).fetchall()
    return [{"id": r.id, "key": r.key, "value": r.value} for r in rows]


@router.get("/api/sys-knowledge/base-knowledge/{item_id}")
async def get_base_knowledge(item_id: int):
    with sys_engine.connect() as conn:
        row = conn.execute(select(base_knowledge).where(base_knowledge.c.id == item_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": row.id, "key": row.key, "value": row.value}


@router.post("/api/sys-knowledge/base-knowledge/")
async def create_base_knowledge(entry: KnowledgeEntry):
    with sys_engine.connect() as conn:
        existing = conn.execute(select(base_knowledge).where(base_knowledge.c.key == entry.key)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"Key '{entry.key}' already exists")
        result = conn.execute(insert(base_knowledge).values(key=entry.key, value=entry.value))
        conn.commit()
        new_id = result.inserted_primary_key[0]
    return {"id": new_id, "key": entry.key, "value": entry.value}


@router.put("/api/sys-knowledge/base-knowledge/{item_id}")
async def update_base_knowledge(item_id: int, entry: KnowledgeUpdate):
    with sys_engine.connect() as conn:
        existing = conn.execute(select(base_knowledge).where(base_knowledge.c.id == item_id)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")
        updates = {}
        if entry.key is not None:
            updates["key"] = entry.key
        if entry.value is not None:
            updates["value"] = entry.value
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        conn.execute(update(base_knowledge).where(base_knowledge.c.id == item_id).values(**updates))
        conn.commit()
        row = conn.execute(select(base_knowledge).where(base_knowledge.c.id == item_id)).fetchone()
    return {"id": row.id, "key": row.key, "value": row.value}


@router.delete("/api/sys-knowledge/base-knowledge/{item_id}")
async def delete_base_knowledge(item_id: int):
    with sys_engine.connect() as conn:
        existing = conn.execute(select(base_knowledge).where(base_knowledge.c.id == item_id)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")
        conn.execute(delete(base_knowledge).where(base_knowledge.c.id == item_id))
        conn.commit()
    return {"deleted": True, "id": item_id}


# ---- db_query_guide CRUD ----

@router.get("/api/sys-knowledge/db-query-guide/")
async def list_db_query_guide():
    with sys_engine.connect() as conn:
        rows = conn.execute(select(db_query_guide).order_by(db_query_guide.c.id)).fetchall()
    return [{"id": r.id, "key": r.key, "value": r.value} for r in rows]


@router.get("/api/sys-knowledge/db-query-guide/{item_id}")
async def get_db_query_guide(item_id: int):
    with sys_engine.connect() as conn:
        row = conn.execute(select(db_query_guide).where(db_query_guide.c.id == item_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return {"id": row.id, "key": row.key, "value": row.value}


@router.post("/api/sys-knowledge/db-query-guide/")
async def create_db_query_guide(entry: KnowledgeEntry):
    with sys_engine.connect() as conn:
        existing = conn.execute(select(db_query_guide).where(db_query_guide.c.key == entry.key)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail=f"Key '{entry.key}' already exists")
        result = conn.execute(insert(db_query_guide).values(key=entry.key, value=entry.value))
        conn.commit()
        new_id = result.inserted_primary_key[0]
    return {"id": new_id, "key": entry.key, "value": entry.value}


@router.put("/api/sys-knowledge/db-query-guide/{item_id}")
async def update_db_query_guide(item_id: int, entry: KnowledgeUpdate):
    with sys_engine.connect() as conn:
        existing = conn.execute(select(db_query_guide).where(db_query_guide.c.id == item_id)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")
        updates = {}
        if entry.key is not None:
            updates["key"] = entry.key
        if entry.value is not None:
            updates["value"] = entry.value
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        conn.execute(update(db_query_guide).where(db_query_guide.c.id == item_id).values(**updates))
        conn.commit()
        row = conn.execute(select(db_query_guide).where(db_query_guide.c.id == item_id)).fetchone()
    return {"id": row.id, "key": row.key, "value": row.value}


@router.delete("/api/sys-knowledge/db-query-guide/{item_id}")
async def delete_db_query_guide(item_id: int):
    with sys_engine.connect() as conn:
        existing = conn.execute(select(db_query_guide).where(db_query_guide.c.id == item_id)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Not found")
        conn.execute(delete(db_query_guide).where(db_query_guide.c.id == item_id))
        conn.commit()
    return {"deleted": True, "id": item_id}


# ---- code_guide CRUD ----

_GUIDE_TABLES = {
    "code-guide": code_guide,
    "graph-code-guide": graph_code_guide,
    "think-guide": think_guide,
    "doc-guide": doc_guide,
}


def _register_guide_crud(guide_name: str, table):
    route_prefix = f"/api/sys-knowledge/{guide_name}"

    @router.get(f"{route_prefix}/")
    async def list_guide():
        with sys_engine.connect() as conn:
            rows = conn.execute(select(table).order_by(table.c.id)).fetchall()
        return [{"id": r.id, "key": r.key, "value": r.value} for r in rows]

    @router.get(f"{route_prefix}/{{item_id}}")
    async def get_guide(item_id: int):
        with sys_engine.connect() as conn:
            row = conn.execute(select(table).where(table.c.id == item_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Not found")
        return {"id": row.id, "key": row.key, "value": row.value}

    @router.post(f"{route_prefix}/")
    async def create_guide(entry: KnowledgeEntry):
        with sys_engine.connect() as conn:
            existing = conn.execute(select(table).where(table.c.key == entry.key)).fetchone()
            if existing:
                raise HTTPException(status_code=409, detail=f"Key '{entry.key}' already exists")
            result = conn.execute(insert(table).values(key=entry.key, value=entry.value))
            conn.commit()
            new_id = result.inserted_primary_key[0]
        return {"id": new_id, "key": entry.key, "value": entry.value}

    @router.put(f"{route_prefix}/{{item_id}}")
    async def update_guide(item_id: int, entry: KnowledgeUpdate):
        with sys_engine.connect() as conn:
            existing = conn.execute(select(table).where(table.c.id == item_id)).fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Not found")
            updates = {}
            if entry.key is not None:
                updates["key"] = entry.key
            if entry.value is not None:
                updates["value"] = entry.value
            if not updates:
                raise HTTPException(status_code=400, detail="No fields to update")
            conn.execute(update(table).where(table.c.id == item_id).values(**updates))
            conn.commit()
            row = conn.execute(select(table).where(table.c.id == item_id)).fetchone()
        return {"id": row.id, "key": row.key, "value": row.value}

    @router.delete(f"{route_prefix}/{{item_id}}")
    async def delete_guide(item_id: int):
        with sys_engine.connect() as conn:
            existing = conn.execute(select(table).where(table.c.id == item_id)).fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Not found")
            conn.execute(delete(table).where(table.c.id == item_id))
            conn.commit()
        return {"deleted": True, "id": item_id}


for guide_name, table in _GUIDE_TABLES.items():
    _register_guide_crud(guide_name, table)


# ---- brief_info (edit-only, no create/delete) ----

class BriefInfoUpdate(BaseModel):
    value: str


@router.get("/api/sys-knowledge/brief-info/")
async def list_brief_info():
    with sys_engine.connect() as conn:
        rows = conn.execute(select(brief_info).order_by(brief_info.c.attr)).fetchall()
    return [{"attr": r.attr, "value": r.value or ""} for r in rows]


@router.put("/api/sys-knowledge/brief-info/{attr}")
async def update_brief_info(attr: str, entry: BriefInfoUpdate):
    with sys_engine.connect() as conn:
        existing = conn.execute(select(brief_info).where(brief_info.c.attr == attr)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Attribute '{attr}' not found")
        conn.execute(update(brief_info).where(brief_info.c.attr == attr).values(value=entry.value))
        conn.commit()
    return {"attr": attr, "value": entry.value}