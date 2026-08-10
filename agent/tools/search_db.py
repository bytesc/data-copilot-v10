import re
from typing import Optional, List, Dict

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError


def _get_all_table_names(engine, tables=None):
    inspector = inspect(engine)
    all_names = inspector.get_table_names()
    if tables:
        return [t for t in all_names if t in tables]
    return all_names


def _get_table_columns(engine, table_name):
    inspector = inspect(engine)
    columns = inspector.get_columns(table_name)
    pk = inspector.get_pk_constraint(table_name)
    pk_cols = set(pk.get('constrained_columns', []))
    fks = inspector.get_foreign_keys(table_name)
    fk_map = {}
    for fk in fks:
        for i, col in enumerate(fk.get('constrained_columns', [])):
            ref_table = fk.get('referred_table', '')
            ref_col = fk.get('referred_columns', [])[i] if i < len(fk.get('referred_columns', [])) else ''
            fk_map[col] = f"{ref_table}.{ref_col}"
    table_comment = inspector.get_table_comment(table_name)
    comment = (table_comment.get('text') or '') if table_comment else ''
    return {
        'table_name': table_name,
        'comment': comment,
        'columns': columns,
        'pk_cols': pk_cols,
        'fk_map': fk_map,
    }


def _get_sample_rows(engine, table_name, columns, limit=3):
    try:
        col_names = [c['name'] for c in columns]
        cols_str = ', '.join(f'`{c}`' for c in col_names)
        query = text(f"SELECT {cols_str} FROM `{table_name}` LIMIT {limit}")
        with engine.connect() as conn:
            result = conn.execute(query)
            rows = [dict(row._mapping) for row in result.fetchall()]
        return rows
    except SQLAlchemyError:
        return []


def _truncate_val(val, max_len=60):
    s = str(val)
    if len(s) > max_len:
        return s[:max_len - 3] + '...'
    return s


def get_db_overview_markdown(engine, tables=None, include_samples=True) -> str:
    table_names = _get_all_table_names(engine, tables)
    if not table_names:
        return "*(No database tables found)*"

    lines = []
    for tname in table_names:
        info = _get_table_columns(engine, tname)
        columns = info['columns']
        pk_cols = info['pk_cols']
        fk_map = info['fk_map']
        comment = info['comment']

        header = f"## {tname}"
        if comment:
            header += f" — {comment}"
        lines.append(header)
        lines.append("")

        header_row = "| Column | Type | Key | Comment |"
        sep_row = "|--------|------|-----|---------|"
        lines.append(header_row)
        lines.append(sep_row)

        for col in columns:
            col_name = col['name']
            col_type = str(col['type'])
            key = ''
            if col_name in pk_cols:
                key = 'PK'
            if col_name in fk_map:
                key = f'FK → {fk_map[col_name]}' if key else f'FK → {fk_map[col_name]}'
            elif col_name in pk_cols and col_name in fk_map:
                key = f'PK, FK → {fk_map[col_name]}'
            col_comment = col.get('comment') or ''
            lines.append(f"| `{col_name}` | {col_type} | {key} | {col_comment} |")

        lines.append("")

        if include_samples:
            samples = _get_sample_rows(engine, tname, columns, 3)
            if samples:
                lines.append("**Sample rows:**")
                lines.append("")
                sample_cols = [c['name'] for c in columns]
                sample_header = "| " + " | ".join(f"`{c}`" for c in sample_cols) + " |"
                sample_sep = "|" + "|".join(["-----"] * len(sample_cols)) + "|"
                lines.append(sample_header)
                lines.append(sample_sep)
                for row in samples:
                    vals = [_truncate_val(row.get(c, '')) for c in sample_cols]
                    lines.append("| " + " | ".join(vals) + " |")
                lines.append("")

    return "\n".join(lines)


def search_db_markdown(engine, keyword: str, tables=None) -> str:
    table_names = _get_all_table_names(engine, tables)
    if not table_names:
        return "*(No database tables found)*"

    kw_lower = keyword.lower()
    matched_tables = []
    matched_columns = {}

    for tname in table_names:
        info = _get_table_columns(engine, tname)
        comment = info['comment']
        columns = info['columns']

        table_match = kw_lower in tname.lower() or kw_lower in comment.lower()
        col_matches = []
        for col in columns:
            col_comment = col.get('comment') or ''
            if kw_lower in col['name'].lower() or kw_lower in col_comment.lower():
                col_matches.append(col)

        if table_match or col_matches:
            matched_tables.append(tname)
            if col_matches:
                matched_columns[tname] = col_matches

    if not matched_tables:
        return f"*(No tables or columns found matching keyword: `{keyword}`)*"

    lines = [f"## Search Results for: `{keyword}`", ""]
    for tname in matched_tables:
        info = _get_table_columns(engine, tname)
        comment = info['comment']
        pk_cols = info['pk_cols']
        fk_map = info['fk_map']

        header = f"### {tname}"
        if comment:
            header += f" — {comment}"
        lines.append(header)
        lines.append("")

        cols_to_show = matched_columns.get(tname, info['columns'])
        header_row = "| Column | Type | Key | Comment |"
        sep_row = "|--------|------|-----|---------|"
        lines.append(header_row)
        lines.append(sep_row)

        for col in cols_to_show:
            col_name = col['name']
            col_type = str(col['type'])
            key = ''
            if col_name in pk_cols:
                key = 'PK'
            if col_name in fk_map:
                key = f'FK → {fk_map[col_name]}' if not key else f'{key}, FK → {fk_map[col_name]}'
            col_comment = col.get('comment') or ''
            lines.append(f"| `{col_name}` | {col_type} | {key} | {col_comment} |")

        lines.append("")

    return "\n".join(lines)


def get_db_summary_for_agent(engine, tables=None) -> str:
    table_names = _get_all_table_names(engine, tables)
    if not table_names:
        return "*(No database tables available)*"

    lines = ["## Database Summary", ""]
    lines.append("| Table | Description | Cols | Key Columns |")
    lines.append("|-------|-------------|------|-------------|")

    for tname in table_names:
        info = _get_table_columns(engine, tname)
        comment = info['comment'] or '—'
        pk_cols = info['pk_cols']
        col_names = [c['name'] for c in info['columns']]
        key_cols = [c for c in col_names if c in pk_cols]
        key_preview = ', '.join(f'`{c}`' for c in key_cols[:3]) if key_cols else '—'
        lines.append(f"| **{tname}** | {comment} | {len(col_names)} | {key_preview} |")

    lines.append("")
    lines.append("Use `search_db` to explore table schemas and sample data in detail.")
    return "\n".join(lines)


def search_db_selected_fields(engine, keyword: Optional[str] = None, tables=None) -> Dict:
    if not keyword or not keyword.strip():
        return {}

    table_names = _get_all_table_names(engine, tables)
    kw_lower = keyword.strip().lower()
    selected = {}

    for tname in table_names:
        info = _get_table_columns(engine, tname)
        comment = info['comment']
        columns = info['columns']

        table_match = kw_lower in tname.lower() or kw_lower in comment.lower()
        col_matches = []
        for col in columns:
            col_comment = col.get('comment') or ''
            if kw_lower in col['name'].lower() or kw_lower in col_comment.lower():
                col_matches.append(col['name'])

        if table_match or col_matches:
            if col_matches:
                selected[tname] = col_matches
            else:
                selected[tname] = []

    return selected if selected else {}