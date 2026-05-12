from jinja2 import Template


def render_sql_template(sql_template: str, params: dict) -> tuple[str, dict]:
    template = Template(sql_template)
    rendered = template.render(**params)

    bind_params = {}
    for key, value in params.items():
        if value is not None and value != "":
            bind_params[key] = value

    return rendered, bind_params
