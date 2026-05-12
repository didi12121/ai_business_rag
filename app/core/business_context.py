from sqlalchemy import text

from app.database import SessionLocal


def load_table_schemas():
    db = SessionLocal()
    try:
        return [
            dict(row._mapping)
            for row in db.execute(
                text(
                    "SELECT table_name, business_name, description, example_question "
                    "FROM ai_table_schema WHERE enabled = 1"
                )
            ).fetchall()
        ]
    finally:
        db.close()


def load_field_schemas():
    db = SessionLocal()
    try:
        return [
            dict(row._mapping)
            for row in db.execute(
                text(
                    "SELECT table_name, field_name, business_name, description, "
                    "value_mapping, example_value "
                    "FROM ai_field_schema WHERE enabled = 1"
                )
            ).fetchall()
        ]
    finally:
        db.close()


def load_business_rules():
    db = SessionLocal()
    try:
        return [
            dict(row._mapping)
            for row in db.execute(
                text(
                    "SELECT rule_name, rule_type, rule_content, related_tables, priority "
                    "FROM ai_business_rule WHERE enabled = 1 ORDER BY priority DESC"
                )
            ).fetchall()
        ]
    finally:
        db.close()


def load_query_template(intent_code: str):
    db = SessionLocal()
    try:
        row = db.execute(
            text(
                "SELECT template_name, intent_code, description, sql_template, "
                "param_schema, result_description "
                "FROM ai_query_template WHERE intent_code = :code AND enabled = 1"
            ),
            {"code": intent_code},
        ).fetchone()
        return dict(row._mapping) if row else None
    finally:
        db.close()
