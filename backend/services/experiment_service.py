"""实验记录服务 — 管理研究实验的记录、对比和搜索"""
import uuid
import time
import json
import aiosqlite
from typing import Optional
from loguru import logger

from backend.database import get_db, DB_PATH
from backend.models.experiment import ExperimentCreate


class ExperimentService:
    """实验管理服务"""
    
    async def create(self, req: ExperimentCreate) -> dict:
        """创建实验记录"""
        exp_id = str(uuid.uuid4())
        now = int(time.time() * 1000)
        
        db = await get_db()
        await db.execute(
            """INSERT INTO experiments 
            (id, source, source_id, name, note, tags, params_json, metrics_json, status, created_at) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (exp_id, req.source, req.source_id, req.name, req.note,
             json.dumps(req.tags), json.dumps(req.params), json.dumps(req.metrics),
             "completed", now)
        )
        await db.commit()
        await db.close()
        
        return {"id": exp_id, "name": req.name, "source": req.source}
    
    async def list_experiments(
        self,
        source: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """列出实验记录"""
        db = await get_db()
        
        if source:
            cursor = await db.execute(
                "SELECT * FROM experiments WHERE source = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (source, limit, offset)
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM experiments ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
        
        rows = await cursor.fetchall()
        await db.close()
        
        results = []
        for row in rows:
            d = dict(row)
            d["tags"] = json.loads(d.get("tags", "[]"))
            d["params"] = json.loads(d.get("params_json", "{}"))
            d["metrics"] = json.loads(d.get("metrics_json", "{}"))
            results.append(d)
        
        return results
    
    async def get_experiment(self, exp_id: str) -> Optional[dict]:
        """获取单个实验详情"""
        db = await get_db()
        cursor = await db.execute("SELECT * FROM experiments WHERE id = ?", (exp_id,))
        row = await cursor.fetchone()
        await db.close()
        
        if not row:
            return None
        
        d = dict(row)
        d["tags"] = json.loads(d.get("tags", "[]"))
        d["params"] = json.loads(d.get("params_json", "{}"))
        d["metrics"] = json.loads(d.get("metrics_json", "{}"))
        return d
    
    async def add_note(self, exp_id: str, note: str) -> bool:
        """添加备注"""
        db = await get_db()
        await db.execute("UPDATE experiments SET note = ? WHERE id = ?", (note, exp_id))
        await db.commit()
        await db.close()
        return True
    
    async def compare(self, experiment_ids: list[str]) -> dict:
        """多实验对比"""
        experiments = []
        for exp_id in experiment_ids:
            exp = await self.get_experiment(exp_id)
            if exp:
                experiments.append(exp)
        
        if len(experiments) < 2:
            return {"error": "至少需要 2 个实验进行对比", "experiments": experiments}
        
        # 参数差异
        all_param_keys = set()
        for exp in experiments:
            all_param_keys.update(exp["params"].keys())
        
        param_diffs = {}
        for key in all_param_keys:
            values = {}
            for exp in experiments:
                values[exp["id"]] = exp["params"].get(key)
            unique_values = set(str(v) for v in values.values())
            param_diffs[key] = {
                "values": values,
                "has_diff": len(unique_values) > 1,
            }
        
        # 指标对比
        all_metric_keys = set()
        for exp in experiments:
            all_metric_keys.update(exp["metrics"].keys())
        
        metric_comparison = {}
        for key in all_metric_keys:
            values = {}
            for exp in experiments:
                values[exp["id"]] = exp["metrics"].get(key)
            metric_comparison[key] = values
        
        return {
            "experiments": experiments,
            "param_diffs": param_diffs,
            "metric_comparison": metric_comparison,
        }
    
    async def search(
        self,
        tags: Optional[list[str]] = None,
        metric_min: Optional[dict] = None,
        limit: int = 50,
    ) -> list[dict]:
        """搜索实验"""
        experiments = await self.list_experiments(limit=200)
        
        results = []
        for exp in experiments:
            # 标签过滤
            if tags:
                if not any(t in exp["tags"] for t in tags):
                    continue
            
            # 指标过滤
            if metric_min:
                skip = False
                for key, min_val in metric_min.items():
                    if exp["metrics"].get(key, 0) < min_val:
                        skip = True
                        break
                if skip:
                    continue
            
            results.append(exp)
            
            if len(results) >= limit:
                break
        
        return results


# 全局单例
experiment_service = ExperimentService()
