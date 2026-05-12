import json
import time
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text

from app.database import SessionLocal
from app.llm.openai_compatible import create_llm_client
from app.core.sys_config import get_ai_config
from app.core.sql_safety import check_sql_safety, build_display_sql, is_modification_request
from app.core.query_planner import generate_query_plan
from app.core.query_plan_validator import validate_and_fix_plan
from app.core.agent_sql_builder import build_step_sql
from app.core.agent_answer import generate_final_answer


def _normalize_value(value):
    if isinstance(value, Decimal): return float(value)
    if isinstance(value, datetime): return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date): return value.strftime("%Y-%m-%d")
    return value


def _save_agent_run(session_id, user_id, question, plan, answer,
                    success, error_code, error_msg, duration_ms):
    db = SessionLocal()
    try:
        db.execute(text(
            "INSERT INTO ai_agent_run "
            "(session_id, user_id, question, query_mode, plan_json, "
            "final_answer, success, error_code, error_msg, duration_ms, "
            "model_name, create_time) VALUES "
            "(:s, :u, :q, 'agent', :p, :a, :ok, :ec, :em, :dur, :mn, NOW())"
        ), {
            "s": session_id, "u": user_id, "q": question,
            "p": json.dumps(plan, ensure_ascii=False),
            "a": answer, "ok": 1 if success else 0,
            "ec": error_code, "em": error_msg, "dur": duration_ms,
            "mn": "llm",
        })
        db.commit()
        run_id = db.execute(text("SELECT LAST_INSERT_ID()")).fetchone()[0]
        return run_id
    except Exception:
        db.rollback()
        return None
    finally:
        db.close()


def _save_step_log(run_id, step_id, step_name, purpose, sql_text,
                   used_tables, row_count, rows_preview, estimated_rows,
                   success, error_code, error_msg, duration_ms):
    db = SessionLocal()
    try:
        db.execute(text(
            "INSERT INTO ai_agent_step_log "
            "(run_id, step_id, step_name, purpose, sql_text, used_tables, "
            "row_count, rows_preview, estimated_rows, success, "
            "error_code, error_msg, duration_ms, create_time) VALUES "
            "(:r, :si, :sn, :p, :st, :ut, :rc, :rp, :er, :ok, "
            ":ec, :em, :d, NOW())"
        ), {
            "r": run_id, "si": step_id, "sn": step_name, "p": purpose,
            "st": sql_text,
            "ut": json.dumps(used_tables) if used_tables else None,
            "rc": row_count,
            "rp": json.dumps(rows_preview, ensure_ascii=False, default=str) if rows_preview else None,
            "er": estimated_rows,
            "ok": 1 if success else 0, "ec": error_code, "em": error_msg,
            "d": duration_ms,
        })
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


async def run_data_agent(
    question: str,
    session_id: str | None = None,
    user_id: str | None = None,
    show_sql: bool | None = None,
) -> dict:
    t0 = time.time()
    config = get_ai_config()
    max_steps = config.get("agent.max_steps", 5)
    default_limit = config.get("agent.default_limit", 100)
    max_rows = config.get("free_sql.max_rows", 200)

    # Reject modifications
    if is_modification_request(question):
        duration_ms = int((time.time() - t0) * 1000)
        return {
            "success": False, "queryMode": "agent",
            "question": question, "answer": "当前 AI 模块只支持查询和分析，不支持修改业务数据。",
            "errorCode": "REJECTED", "errorMsg": "修改类请求", "durationMs": duration_ms,
        }

    # Generate query plan
    plan = await generate_query_plan(question)

    if not plan.get("canAnswer"):
        duration_ms = int((time.time() - t0) * 1000)
        return {
            "success": False, "queryMode": "agent",
            "question": question, "plan": plan,
            "answer": f"无法回答：{plan.get('reason', '未知原因')}",
            "errorCode": "QUERY_PLAN_FAILED", "errorMsg": plan.get("reason", ""),
            "durationMs": duration_ms,
        }

    # Validate plan
    plan = validate_and_fix_plan(plan, question, max_limit=default_limit)
    steps = plan.get("steps", [])

    observations = []
    step_logs = []
    all_sqls = []

    for step in steps[:max_steps]:
        step_t0 = time.time()
        sid = step.get("stepId", len(observations) + 1)

        # Build SQL
        sql_result = await build_step_sql(question, plan, step, observations)

        if not sql_result.get("canGenerate") or not sql_result.get("sql"):
            step_logs.append({
                "stepId": sid, "name": step.get("name", ""),
                "purpose": step.get("purpose", ""),
                "success": False, "errorCode": "SQL_BUILDER_FAILED",
                "errorMsg": sql_result.get("reason", ""),
                "sql": None, "rowCount": 0, "rowsPreview": [],
                "usedTables": sql_result.get("usedTables", []),
                "riskLevel": sql_result.get("riskLevel", "high"),
                "durationMs": int((time.time() - step_t0) * 1000),
            })
            _save_step_log(
                None, sid, step.get("name", ""), step.get("purpose", ""),
                None, sql_result.get("usedTables", []), 0, None, None,
                False, "SQL_BUILDER_FAILED", sql_result.get("reason", ""),
                int((time.time() - step_t0) * 1000),
            )
            continue

        step_sql = sql_result["sql"]

        # Safety check
        try:
            step_sql = check_sql_safety(step_sql, max_rows=max_rows, is_free_sql=True)
        except Exception as e:
            step_logs.append({
                "stepId": sid, "name": step.get("name", ""),
                "purpose": step.get("purpose", ""),
                "success": False, "errorCode": "SQL_SAFETY_ERROR",
                "errorMsg": str(e), "sql": step_sql,
                "rowCount": 0, "rowsPreview": [],
                "usedTables": sql_result.get("usedTables", []),
                "riskLevel": sql_result.get("riskLevel", "high"),
                "durationMs": int((time.time() - step_t0) * 1000),
            })
            continue

        display_sql = build_display_sql(step_sql, sql_result.get("params", {}))
        all_sqls.append(display_sql)

        # EXPLAIN
        estimated_rows = None
        if config.get("free_sql.explain_before_run", True):
            db = SessionLocal()
            try:
                explain_result = db.execute(text(f"EXPLAIN {step_sql}")).fetchall()
                total = 0
                for r in explain_result:
                    try:
                        total += int(r._mapping.get("rows", 0) or 0)
                    except (ValueError, TypeError):
                        pass
                estimated_rows = total
                max_est = config.get("free_sql.max_estimated_rows", 50000)
                if estimated_rows > max_est:
                    step_logs.append({
                        "stepId": sid, "name": step.get("name", ""),
                        "purpose": step.get("purpose", ""),
                        "success": False, "errorCode": "SQL_TOO_LARGE",
                        "errorMsg": f"预估扫描 {estimated_rows} 行 > {max_est}",
                        "sql": display_sql,
                        "estimatedRows": estimated_rows,
                        "rowCount": 0, "rowsPreview": [],
                        "usedTables": sql_result.get("usedTables", []),
                        "riskLevel": sql_result.get("riskLevel", "high"),
                        "durationMs": int((time.time() - step_t0) * 1000),
                    })
                    db.close()
                    continue
            except Exception as e:
                step_logs.append({
                    "stepId": sid, "name": step.get("name", ""),
                    "purpose": step.get("purpose", ""),
                    "success": False, "errorCode": "SQL_EXPLAIN_ERROR",
                    "errorMsg": str(e), "sql": display_sql,
                    "rowCount": 0, "rowsPreview": [],
                    "usedTables": sql_result.get("usedTables", []),
                    "riskLevel": sql_result.get("riskLevel", "high"),
                    "durationMs": int((time.time() - step_t0) * 1000),
                })
                db.close()
                continue
            finally:
                try: db.close()
                except: pass

        # Execute
        db = SessionLocal()
        try:
            db.execute(text("SET SESSION max_execution_time = :t"),
                       {"t": config.get("sql.timeout_seconds", 10) * 1000})
            result = db.execute(text(step_sql))
            rows_raw = result.fetchall()
            columns = list(result.keys())
            rows = [dict(zip(columns, r)) for r in rows_raw]
        except Exception as e:
            step_logs.append({
                "stepId": sid, "name": step.get("name", ""),
                "purpose": step.get("purpose", ""),
                "success": False, "errorCode": "SQL_EXECUTE_ERROR",
                "errorMsg": str(e), "sql": display_sql,
                "estimatedRows": estimated_rows,
                "rowCount": 0, "rowsPreview": [],
                "usedTables": sql_result.get("usedTables", []),
                "riskLevel": sql_result.get("riskLevel", "high"),
                "durationMs": int((time.time() - step_t0) * 1000),
            })
            db.close()
            continue
        finally:
            try: db.close()
            except: pass

        step_duration = int((time.time() - step_t0) * 1000)
        normalized_rows = [{k: _normalize_value(v) for k, v in r.items()} for r in rows]

        observation = {
            "stepId": sid, "name": step.get("name", ""),
            "purpose": step.get("purpose", ""),
            "sql": display_sql if config.get("agent.show_step_sql", True) else None,
            "rows": normalized_rows[:20],
            "rowCount": len(rows),
            "usedTables": sql_result.get("usedTables", []),
            "riskLevel": sql_result.get("riskLevel", "low"),
            "estimatedRows": estimated_rows,
            "durationMs": step_duration,
        }
        observations.append(observation)

        step_logs.append({
            "stepId": sid, "name": step.get("name", ""),
            "purpose": step.get("purpose", ""),
            "success": True, "errorCode": None, "errorMsg": None,
            "sql": display_sql,
            "estimatedRows": estimated_rows,
            "rowCount": len(rows), "rowsPreview": normalized_rows[:20],
            "usedTables": sql_result.get("usedTables", []),
            "riskLevel": sql_result.get("riskLevel", "low"),
            "durationMs": step_duration,
        })

    # Generate final answer
    if observations:
        try:
            answer = await generate_final_answer(question, plan, observations)
        except Exception as e:
            answer = f"回答生成失败：{e}"
            success = False
    else:
        answer = "未能获取任何有效数据来回答该问题。"
        success = False

    success = all(s.get("success", False) for s in step_logs) if step_logs else False
    duration_ms = int((time.time() - t0) * 1000)

    # Save logs
    run_id = _save_agent_run(
        session_id, user_id, question, plan, answer,
        success, None if success else "AGENT_ERROR", "" if success else "部分步骤失败",
        duration_ms,
    )
    if run_id:
        for log in step_logs:
            _save_step_log(
                run_id, log["stepId"], log["name"], log["purpose"],
                log.get("sql"), log.get("usedTables", []),
                log.get("rowCount", 0), log.get("rowsPreview", []),
                log.get("estimatedRows"), log.get("success", False),
                log.get("errorCode"), log.get("errorMsg"),
                log.get("durationMs", 0),
            )

    return {
        "success": success,
        "queryMode": "agent",
        "question": question,
        "answer": answer,
        "plan": plan if config.get("agent.show_plan", True) else None,
        "observations": observations,
        "steps": step_logs,
        "durationMs": duration_ms,
    }
