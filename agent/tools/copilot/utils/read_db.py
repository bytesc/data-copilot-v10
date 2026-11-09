import pandas as pd
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError

tables_data = None


def get_all_table_names(engine):
    inspector = inspect(engine)
    return inspector.get_table_names()


# def get_rows_from_all_tables(engine, tables, num=3):
#     # 获取所有表名
#     inspector = inspect(engine)
#     if not tables:
#         table_names = inspector.get_table_names()
#     else:
#         table_names = tables
#
#     # 准备一个字典来存储每个表的前5行数据
#     first_five_rows = {}
#
#     # 遍历所有表名
#     for table_name in table_names:
#         try:
#             # 构造查询语句，限制返回5行
#             query = text(f"SELECT * FROM {table_name} LIMIT {num}")
#
#             # 使用 pandas 读取查询结果
#             with engine.connect() as connection:
#                 df = pd.read_sql(query, connection)
#
#             # 将结果存储到字典中
#             first_five_rows[table_name] = df
#
#         except SQLAlchemyError as e:
#             # 如果发生错误，打印错误信息并继续处理下一个表
#             print(f"An error occurred while fetching data from table {table_name}: {e}")
#             continue
#
#     return first_five_rows
def _quote_ident(name):
    """Quote a MySQL identifier, doubling embedded backticks."""
    return "`" + str(name).replace("`", "``") + "`"


def _filter_real_tables(inspector, tables):
    """Intersect a caller-supplied table list with the real database tables.

    User/LLM-supplied table lists may contain names that do not exist (typos,
    hallucinated names). Querying metadata for a missing table raises
    NoSuchTableError and would abort prompt building, so every schema-prompt
    helper must filter through this first. Returns all real tables when
    ``tables`` is empty/None (same convention as before).
    """
    real_tables = set(inspector.get_table_names())
    if not tables:
        return list(real_tables)
    valid = [t for t in tables if t in real_tables]
    skipped = [t for t in tables if t not in real_tables]
    if skipped:
        print(f"[WARNING] Requested tables not found in database (skipped): {skipped}")
    return valid


def get_rows_from_all_tables(engine, tables, num=3, selected_fields=None):
    inspector = inspect(engine)
    table_names = _filter_real_tables(inspector, tables)

    if selected_fields:
        table_names = [t for t in table_names if t in selected_fields]

    try:
        limit = max(1, int(num))
    except (TypeError, ValueError):
        limit = 3

    first_five_rows = {}
    for table_name in table_names:
        try:
            valid_cols = {c["name"] for c in inspector.get_columns(table_name)}
            cols = None
            if selected_fields and table_name in selected_fields:
                requested = selected_fields[table_name]
                if requested:
                    cols = [c for c in requested if c in valid_cols]
            if cols:
                cols_str = ", ".join(_quote_ident(c) for c in cols)
                query = text(f"SELECT {cols_str} FROM {_quote_ident(table_name)} LIMIT {limit}")
            else:
                query = text(f"SELECT * FROM {_quote_ident(table_name)} LIMIT {limit}")
            with engine.connect() as connection:
                df = pd.read_sql(query, connection)
            for col in df.columns:
                if df[col].dtype == object:
                    df[col] = df[col].apply(lambda x: x[:37] + '...' if isinstance(x, str) and len(x) > 40 else x)
            first_five_rows[table_name] = df

        except SQLAlchemyError as e:
            print(f"An error occurred while fetching data from table {table_name}: {e}")
            continue
    return first_five_rows


def get_foreign_keys(engine, tables):
    inspector = inspect(engine)
    table_names = _filter_real_tables(inspector, tables)
    foreign_keys = {}
    for table_name in table_names:
        fks = inspector.get_foreign_keys(table_name)
        if fks:
            foreign_keys[table_name] = {}
            for fk in fks:
                for i in range(len(fk['constrained_columns'])):
                    foreign_keys[table_name][table_name + "." + fk['constrained_columns'][i]] = \
                        fk['referred_table'] + "." + fk['referred_columns'][i]

    return foreign_keys


def get_table_and_column_comments(engine, tables, selected_fields=None):
    inspector = inspect(engine)
    table_names = _filter_real_tables(inspector, tables)

    if selected_fields:
        table_names = [t for t in table_names if t in selected_fields]

    table_comments = {}
    column_comments = {}

    for table_name in table_names:
        table_comment = inspector.get_table_comment(table_name)
        if table_comment['text'] is not None:
            table_comments[table_name] = table_comment['text']
        columns = inspector.get_columns(table_name)

        if selected_fields and table_name in selected_fields:
            allowed_cols = selected_fields[table_name]
            if allowed_cols:
                allowed_cols = set(allowed_cols)
                columns = [c for c in columns if c['name'] in allowed_cols]

        column_comments[table_name] = {}
        for column in columns:
            if column['comment'] is not None:
                column_comments[table_name][column['name']] = column['comment']
        if not column_comments[table_name]:
            del column_comments[table_name]
    table_comments = {k: v for k, v in table_comments.items() if v is not None}
    return [table_comments, column_comments]


def get_table_creation_statements(engine, tables, simple=False, selected_fields=None):
    inspector = inspect(engine)
    table_names = _filter_real_tables(inspector, tables)

    if selected_fields:
        table_names = [t for t in table_names if t in selected_fields]

    creation_statements = {}

    for table_name in table_names:
        columns = inspector.get_columns(table_name)
        primary_keys = inspector.get_pk_constraint(table_name)
        foreign_keys = inspector.get_foreign_keys(table_name)

        if selected_fields and table_name in selected_fields:
            allowed_cols = selected_fields[table_name]
            if allowed_cols:
                allowed_cols = set(allowed_cols)
                columns = [c for c in columns if c['name'] in allowed_cols]
                if primary_keys['constrained_columns']:
                    pk_cols = [c for c in primary_keys['constrained_columns'] if c in allowed_cols]
                    primary_keys = {'constrained_columns': pk_cols}
                filtered_fks = []
                for fk in foreign_keys:
                    constrained = [c for c in fk['constrained_columns'] if c in allowed_cols]
                    if constrained:
                        filtered_fks.append({
                            'constrained_columns': constrained,
                            'referred_table': fk['referred_table'],
                            'referred_columns': fk['referred_columns']
                        })
                foreign_keys = filtered_fks

        create_table_statement = f"CREATE TABLE {table_name} (\n"

        column_definitions = []
        for column in columns:
            if not simple:
                column_def = f"    {column['name']} {column['type']}"
                if not column['nullable']:
                    column_def += " NOT NULL"
                if column['default'] is not None:
                    column_def += f" DEFAULT {column['default']}"
            else:
                column_def = f"    {column['name']} {column['type']}"
            column_definitions.append(column_def)

        if not simple:
            if primary_keys['constrained_columns']:
                pk_columns = ", ".join(primary_keys['constrained_columns'])
                column_definitions.append(f"    PRIMARY KEY ({pk_columns})")

            for fk in foreign_keys:
                fk_columns = ", ".join(fk['constrained_columns'])
                referred_table = fk['referred_table']
                referred_columns = ", ".join(fk['referred_columns'])
                column_definitions.append(
                    f"    FOREIGN KEY ({fk_columns}) REFERENCES {referred_table} ({referred_columns})")

        create_table_statement += ",\n".join(column_definitions)
        create_table_statement += "\n);"

        creation_statements[table_name] = create_table_statement

    return creation_statements

def get_all_comments(engine, tables=None):
    inspector = inspect(engine)
    # 过滤掉不存在的表名，避免产生误导性的空表条目
    table_names = _filter_real_tables(inspector, tables)

    all_comments = {}

    for table_name in table_names:
        try:
            table_info = {}

            # 获取表注释
            table_comment = inspector.get_table_comment(table_name)
            table_info['table_comment'] = table_comment.get('text', '') if table_comment else ''

            # 获取列注释
            columns = inspector.get_columns(table_name)
            column_comments = {}
            for column in columns:
                comment = column.get('comment')
                if comment:
                    column_comments[column['name']] = comment

            table_info['columns'] = column_comments
            all_comments[table_name] = table_info

        except SQLAlchemyError as e:
            print(f"获取表 {table_name} 的注释时出错: {e}")
            all_comments[table_name] = {
                'table_comment': '',
                'columns': {}
            }
            continue

    return all_comments

def get_table_comments_dict(engine, tables=None):
    inspector = inspect(engine)
    table_names = _filter_real_tables(inspector, tables)

    table_comments = {}

    for table_name in table_names:
        try:
            # 获取表注释
            table_comment = inspector.get_table_comment(table_name)
            # 如果注释存在且不为None，则添加到字典中
            if table_comment and table_comment['text'] is not None:
                table_comments[table_name] = table_comment['text']
            else:
                # 如果没有注释，可以设置为空字符串或None
                table_comments[table_name] = ""
        except SQLAlchemyError as e:
            print(f"获取表 {table_name} 的注释时出错: {e}")
            table_comments[table_name] = ""
    return table_comments

# def get_table_creation_statements_2(engine):
#     creation_statements = {}
#     with engine.connect() as connection:
#         # 获取所有表名
#         table_names = inspect(engine).get_table_names()
#         for table_name in table_names:
#             # 使用 SHOW CREATE TABLE 获取建表语句
#             query = text(f"SHOW CREATE TABLE {table_name}")
#             result = connection.execute(query).fetchone()
#             if result:
#                 # 结果中的第二列是建表语句
#                 create_table_statement = result[1]
#                 creation_statements[table_name] = create_table_statement
#     return creation_statements


def execute_sql(engine, sql):
    # 使用连接执行SQL语句
    with engine.connect() as connection:
        try:
            # 执行SQL语句
            result = connection.execute(text(sql))
            # 提交事务（对于INSERT、UPDATE、DELETE等操作）
            connection.commit()
            # 返回影响的行数
            return result.rowcount
        except SQLAlchemyError as e:
            # 如果发生错误，回滚事务
            connection.rollback()
            # 打印错误信息
            print(f"An error occurred: {e}")
            raise e


import pandas as pd
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError


def execute_select(engine, sql):
    """Execute a read-only query against the read-only engine.

    Access control is enforced by the dedicated read-only database account
    (``mysql_readonly``) instead of parsing the SQL text here: a correctly
    scoped account (SELECT/SHOW only, no ``FILE`` privilege) cannot perform
    writes/DDL or ``SELECT ... INTO OUTFILE`` regardless of the statement text.
    A missing read-only account is a hard error so the privileged user is never
    used as a fallback.

    The statement is sent through ``exec_driver_sql`` so SQLAlchemy never parses
    the raw SQL for ``:name`` bind parameters. ``text(sql)`` (or passing a plain
    string to ``pd.read_sql_query``) treats any ``:identifier`` preceded by a
    non-identifier character as a bind parameter (e.g. a literal like ``':x'``
    or JSON content ``{"k": v}``), which raises "A value is required for bind
    parameter" and makes the caller misread it as an execution failure.
    """
    if engine is None:
        raise RuntimeError(
            "No read-only database is configured (mysql_readonly is missing); "
            "refusing to execute SQL. Configure mysql_readonly instead of "
            "falling back to the privileged database user."
        )
    try:
        with engine.connect() as connection:
            result = connection.exec_driver_sql(sql)
            columns = list(result.keys())
            rows = result.fetchall()
        return pd.DataFrame(rows, columns=columns)
    except SQLAlchemyError as e:
        # 如果发生错误，打印错误信息
        print(f"An error occurred: {e}")
        raise e


if __name__ == "__main__":
    # data = get_data_from_db()
    # print(type(data), "\n")
    # print(data[2][1])
    print("###########################################\n\n")
    print(get_table_creation_statements())

    # for table_name, table_df in mdata.items():
    #     print(f"Table: {table_name}")
    #     print(table_df)
    #     print(type(table_df))
