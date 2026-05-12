import json
import time
from collections.abc import Awaitable, Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.database import SessionLocal
from app.core.sys_config import get_ai_config
from app.core.sql_safety import check_sql_safety, build_display_sql, is_modification_request
from app.core.query_planner import generate_query_plan
from app.core.query_plan_validator import validate_and_fix_plan
from app.core.agent_sql_builder import build_step_sql
from app.core.agent_answer import generate_final_answer
from app.core.conversation_memory import add_turn

EventCallback = Callable[[dict[str, Any]], Awaitable[None]] | None


async def _emit(cb: EventCallback, event: str, **kwargs):
    if cb:
        await cb({"event": event, **kwargs})


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


def _save_step_logs(run_id, step_logs):
    if not run_id:
        return
    db = SessionLocal()
    try:
        for log in step_logs:
            db.execute(text(
                "INSERT INTO ai_agent_step_log "
                "(run_id, step_id, step_name, purpose, sql_text, used_tables, "
                "row_count, rows_preview, estimated_rows, success, "
                "error_code, error_msg, duration_ms, create_time) VALUES "
                "(:r, :si, :sn, :p, :st, :ut, :rc, :rp, :er, :ok, "
                ":ec, :em, :d, NOW())"
            ), {
                "r": run_id, "si": log.get("stepId"),
                "sn": log.get("name", ""), "p": log.get("purpose", ""),
                "st": log.get("sql"),
                "ut": json.dumps(log.get("usedTables", [])) if log.get("usedTables") else None,
                "rc": log.get("rowCount", 0),
                "rp": json.dumps(log.get("rowsPreview", []), ensure_ascii=False, default=str) if log.get("rowsPreview") else None,
                "er": log.get("estimatedRows"),
                "ok": 1 if log.get("success", False) else 0,
                "ec": log.get("errorCode"), "em": log.get("errorMsg"),
                "d": log.get("durationMs", 0),
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
    event_callback: EventCallback = None,
    conversation_context: list[dict] | None = None,
) -> dict:
    t0 = time.time()
    cb = event_callback
    config = get_ai_config()
    max_steps = config.get("agent.max_steps", 5)
    default_limit = config.get("agent.default_limit", 100)
    max_rows = config.get("free_sql.max_rows", 200)
    explain_before = config.get("free_sql.explain_before_run", True)
    max_est_rows = config.get("free_sql.max_estimated_rows", 50000)
    timeout_sec = config.get("sql.timeout_seconds", 10)

    # Reject modifications
    if is_modification_request(question):
        await _emit(cb, "error", errorCode="REJECTED", errorMsg="修改类请求")
        return {
            "success": False, "queryMode": "agent",
            "question": question,
            "answer": "当前 AI 模块只支持查询和分析，不支持修改业务数据。",
            "errorCode": "REJECTED", "errorMsg": "修改类请求",
            "durationMs": int((time.time() - t0) * 1000),
        }

    # Planning
    await _emit(cb, "thinking", step="agent", text="AI Agent 正在理解问题...")
    await _emit(cb, "planning_start", text="正在分析问题并生成查询计划...")

    plan = await generate_query_plan(question, conversation_context)
    await _emit(cb, "plan_ready", plan=plan)

    if not plan.get("canAnswer"):
        return {
            "success": False, "queryMode": "agent",
            "question": question, "plan": plan,
            "answer": f"无法回答：{plan.get('reason', '未知原因')}",
            "errorCode": "QUERY_PLAN_FAILED", "errorMsg": plan.get("reason", ""),
            "durationMs": int((time.time() - t0) * 1000),
        }

    # Validate plan
    plan = validate_and_fix_plan(plan, question, max_limit=default_limit)
    steps = plan.get("steps", [])

    def _dependency_satisfied(step: dict, observations: list[dict]) -> tuple:
        depends_on = step.get("dependsOn")
        if not depends_on:
            return True, None
        obs = next((o for o in observations if str(o.get("stepId")) == str(depends_on)), None)
        if not obs:
            return False, f"依赖步骤 {depends_on} 没有成功结果"
        if not obs.get("success", True):
            return False, f"依赖步骤 {depends_on} 执行失败"
        if int(obs.get("rowCount") or 0) <= 0:
            return False, f"依赖步骤 {depends_on} 查询结果为空"
        return True, None

    observations = []
    step_logs = []

    for step in steps[:max_steps]:
        step_t0 = time.time()
        sid = step.get("stepId", len(observations) + 1)

        # Dependency check
        ok, reason = _dependency_satisfied(step, observations)
        if not ok:
            await _emit(cb, "step_skipped", stepId=sid, reason=reason, errorCode="SKIPPED_DEPENDENCY")
            step_logs.append(dict(
                stepId=sid, name=step.get("name", ""), purpose=step.get("purpose", ""),
                success=False, errorCode="SKIPPED_DEPENDENCY", errorMsg=reason,
                sql=None, rowCount=0, rowsPreview=[],
                usedTables=[], riskLevel="low",
                durationMs=int((time.time() - step_t0) * 1000),
            ))
            if step.get("required", True):
                break
            continue

        # Step start
        await _emit(cb, "step_start", stepId=sid, name=step.get("name", ""), purpose=step.get("purpose", ""))

        # Build SQL
        sql_result = await build_step_sql(question, plan, step, observations, conversation_context)
        step_sql = sql_result.get("sql")
        bind_params = sql_result.get("params") or {}

        await _emit(cb, "sql_generated", stepId=sid,
                    sql=step_sql, usedTables=sql_result.get("usedTables", []),
                    reason=sql_result.get("reason", ""),
                    riskLevel=sql_result.get("riskLevel", "low"))

        if not sql_result.get("canGenerate") or not step_sql:
            await _emit(cb, "step_error", stepId=sid, errorCode="SQL_BUILDER_FAILED",
                        errorMsg=sql_result.get("reason", ""))
            step_logs.append(dict(
                stepId=sid, name=step.get("name", ""), purpose=step.get("purpose", ""),
                success=False, errorCode="SQL_BUILDER_FAILED",
                errorMsg=sql_result.get("reason", ""),
                sql=None, rowCount=0, rowsPreview=[],
                usedTables=sql_result.get("usedTables", []),
                riskLevel=sql_result.get("riskLevel", "high"),
                durationMs=int((time.time() - step_t0) * 1000),
            ))
            continue

        # Safety check
        try:
            step_sql = check_sql_safety(step_sql, max_rows=max_rows, is_free_sql=True)
            await _emit(cb, "sql_checked", stepId=sid, success=True, text="SQL 安全检查通过")
        except Exception as e:
            await _emit(cb, "step_error", stepId=sid, errorCode="SQL_SAFETY_ERROR", errorMsg=str(e))
            step_logs.append(dict(
                stepId=sid, name=step.get("name", ""), purpose=step.get("purpose", ""),
                success=False, errorCode="SQL_SAFETY_ERROR", errorMsg=str(e),
                sql=step_sql, rowCount=0, rowsPreview=[],
                usedTables=sql_result.get("usedTables", []),
                riskLevel=sql_result.get("riskLevel", "high"),
                durationMs=int((time.time() - step_t0) * 1000),
            ))
            continue

        display_sql = build_display_sql(step_sql, bind_params)

        # EXPLAIN
        estimated_rows = None
        if explain_before:
            db = SessionLocal()
            try:
                explain_sql_text = f"EXPLAIN {step_sql}"
                explain_result = db.execute(text(explain_sql_text), bind_params).fetchall()
                total = 0
                for r in explain_result:
                    try: total += int(r._mapping.get("rows", 0) or 0)
                    except (ValueError, TypeError): pass
                estimated_rows = total
                await _emit(cb, "explain_done", stepId=sid, estimatedRows=estimated_rows, success=True)
                if estimated_rows > max_est_rows:
                    await _emit(cb, "step_error", stepId=sid, errorCode="SQL_TOO_LARGE",
                                errorMsg=f"预估扫描 {estimated_rows} 行 > {max_est_rows}")
                    step_logs.append(dict(
                        stepId=sid, name=step.get("name", ""), purpose=step.get("purpose", ""),
                        success=False, errorCode="SQL_TOO_LARGE",
                        errorMsg=f"预估扫描 {estimated_rows} 行 > {max_est_rows}",
                        sql=display_sql, estimatedRows=estimated_rows,
                        rowCount=0, rowsPreview=[],
                        usedTables=sql_result.get("usedTables", []),
                        riskLevel=sql_result.get("riskLevel", "high"),
                        durationMs=int((time.time() - step_t0) * 1000),
                    ))
                    db.close()
                    continue
            except Exception as e:
                await _emit(cb, "step_error", stepId=sid, errorCode="SQL_EXPLAIN_ERROR", errorMsg=str(e))
                step_logs.append(dict(
                    stepId=sid, name=step.get("name", ""), purpose=step.get("purpose", ""),
                    success=False, errorCode="SQL_EXPLAIN_ERROR", errorMsg=str(e),
                    sql=display_sql, rowCount=0, rowsPreview=[],
                    usedTables=sql_result.get("usedTables", []),
                    riskLevel=sql_result.get("riskLevel", "high"),
                    durationMs=int((time.time() - step_t0) * 1000),
                ))
                db.close()
                continue
            finally:
                try: db.close()
                except: pass

        # Execute
        db = SessionLocal()
        try:
            db.execute(text("SET SESSION max_execution_time = :t"),
                       {"t": timeout_sec * 1000})
            result = db.execute(text(step_sql), bind_params)
            rows_raw = result.fetchall()
            columns = list(result.keys())
            rows = [dict(zip(columns, r)) for r in rows_raw]
        except Exception as e:
            await _emit(cb, "step_error", stepId=sid, errorCode="SQL_EXECUTE_ERROR", errorMsg=str(e))
            step_logs.append(dict(
                stepId=sid, name=step.get("name", ""), purpose=step.get("purpose", ""),
                success=False, errorCode="SQL_EXECUTE_ERROR", errorMsg=str(e),
                sql=display_sql, estimatedRows=estimated_rows,
                rowCount=0, rowsPreview=[],
                usedTables=sql_result.get("usedTables", []),
                riskLevel=sql_result.get("riskLevel", "high"),
                durationMs=int((time.time() - step_t0) * 1000),
            ))
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
            "success": True,
            "sql": display_sql if config.get("agent.show_step_sql", True) else None,
            "rows": normalized_rows[:20],
            "rowCount": len(rows),
            "usedTables": sql_result.get("usedTables", []),
            "riskLevel": sql_result.get("riskLevel", "low"),
            "estimatedRows": estimated_rows,
            "durationMs": step_duration,
        }
        observations.append(observation)

        await _emit(cb, "step_done", stepId=sid, name=step.get("name", ""),
                    purpose=step.get("purpose", ""),
                    rowCount=len(rows), rowsPreview=normalized_rows[:3],
                    success=True, durationMs=step_duration)

        step_logs.append(dict(
            stepId=sid, name=step.get("name", ""), purpose=step.get("purpose", ""),
            success=True, errorCode=None, errorMsg=None,
            sql=display_sql, estimatedRows=estimated_rows,
            rowCount=len(rows), rowsPreview=normalized_rows[:20],
            usedTables=sql_result.get("usedTables", []),
            riskLevel=sql_result.get("riskLevel", "low"),
            durationMs=step_duration,
        ))

    # Success state
    successful_steps = [s for s in step_logs if s.get("success")]
    failed_steps = [s for s in step_logs if not s.get("success")]
    all_ok = len(successful_steps) > 0 and len(failed_steps) == 0
    partial_success = len(successful_steps) > 0 and len(failed_steps) > 0
    all_failed = len(successful_steps) == 0

    if all_failed:
        success = False
        error_code = "AGENT_ALL_STEPS_FAILED"
        error_msg = "所有步骤均失败"
    elif partial_success:
        success = True
        error_code = None
        error_msg = ""
    else:
        success = all_ok
        error_code = None if all_ok else "AGENT_ERROR"
        error_msg = "" if all_ok else "部分步骤失败"

    # Final answer
    answer = ""
    if observations:
        await _emit(cb, "answer_start", text="正在根据查询结果生成回答...")
        try:
            answer = await generate_final_answer(
                question, plan, observations,
                successful_steps=successful_steps,
                failed_steps=failed_steps,
                partial_success=partial_success,
            )
        except Exception as e:
            answer = f"回答生成失败：{e}"
    else:
        answer = "未能获取任何有效数据来回答该问题。"

    duration_ms = int((time.time() - t0) * 1000)

    # Save logs
    run_id = _save_agent_run(
        session_id, user_id, question, plan, answer,
        success, error_code, error_msg, duration_ms,
    )
    _save_step_logs(run_id, step_logs)

    result = {
        "success": success,
        "partialSuccess": partial_success,
        "queryMode": "agent",
        "question": question,
        "answer": answer,
        "plan": plan if config.get("agent.show_plan", True) else None,
        "observations": observations,
        "steps": step_logs,
        "durationMs": duration_ms,
    }

    # Save to conversation memory
    try:
        add_turn(session_id or "default", {
            "question": question,
            "answer": answer,
            "queryMode": "agent",
            "plan": plan,
            "observations": observations,
        })
    except Exception:
        pass

    await _emit(cb, "done", **result)
    return result
