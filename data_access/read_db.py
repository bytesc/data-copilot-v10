import pandas as pd
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError

from data_access.db_conn import engine


def get_all_table_names():
    inspector = inspect(engine)
    return inspector.get_table_names()


def get_all_comments_from_table(tables=None):
    inspector = inspect(engine)
    # 获取表名列表
    if not tables:
        table_names = inspector.get_table_names()
    else:
        table_names = tables

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

def get_rows_from_all_tables(num=5):
    # 获取所有表名
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    # 准备一个字典来存储每个表的前5行数据
    first_five_rows = {}

    # 遍历所有表名
    for table_name in table_names:
        try:
            # 构造查询语句，限制返回5行
            query = text(f"SELECT * FROM {table_name} LIMIT {num}")

            # 使用 pandas 读取查询结果
            with engine.connect() as connection:
                df = pd.read_sql(query, connection)

            # 将结果存储到字典中
            first_five_rows[table_name] = df

        except SQLAlchemyError as e:
            # 如果发生错误，打印错误信息并继续处理下一个表
            print(f"An error occurred while fetching data from table {table_name}: {e}")
            continue

    return first_five_rows

def get_foreign_keys():
    inspector = inspect(engine)
    foreign_keys = {}
    for table_name in inspector.get_table_names():
        fks = inspector.get_foreign_keys(table_name)
        if fks:
            foreign_keys[table_name] = {}
            for fk in fks:
                for i in range(len(fk['constrained_columns'])):
                    foreign_keys[table_name][table_name+"."+fk['constrained_columns'][i]] = \
                        fk['referred_table']+"."+fk['referred_columns'][i]

    return foreign_keys


def get_table_and_column_comments():
    inspector = inspect(engine)
    table_comments = {}
    column_comments = {}
    table_names = inspector.get_table_names()
    for table_name in table_names:
        table_comment = inspector.get_table_comment(table_name)
        table_comments[table_name] = table_comment['text']
        columns = inspector.get_columns(table_name)
        column_comments[table_name] = {}
        for column in columns:
            column_comments[table_name][column['name']] = column['comment']
    return [table_comments, column_comments]


def get_table_comments_dict(tables=None):
    inspector = inspect(engine)
    if not tables:
        table_names = inspector.get_table_names()
    else:
        table_names = tables

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


def get_table_creation_statements():
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    creation_statements = {}

    for table_name in table_names:
        # 获取表的列信息
        columns = inspector.get_columns(table_name)
        # 获取表的主键信息
        primary_keys = inspector.get_pk_constraint(table_name)
        # 获取表的外键信息
        foreign_keys = inspector.get_foreign_keys(table_name)
        # 获取表的索引信息
        indexes = inspector.get_indexes(table_name)

        # 开始构建建表语句
        create_table_statement = f"CREATE TABLE {table_name} (\n"

        # 添加列定义
        column_definitions = []
        for column in columns:
            column_def = f"    {column['name']} {column['type']}"
            if not column['nullable']:
                column_def += " NOT NULL"
            if column['default'] is not None:
                column_def += f" DEFAULT {column['default']}"
            column_definitions.append(column_def)

        # 添加主键定义
        if primary_keys['constrained_columns']:
            pk_columns = ", ".join(primary_keys['constrained_columns'])
            column_definitions.append(f"    PRIMARY KEY ({pk_columns})")

        # 添加外键定义
        for fk in foreign_keys:
            fk_columns = ", ".join(fk['constrained_columns'])
            referred_table = fk['referred_table']
            referred_columns = ", ".join(fk['referred_columns'])
            column_definitions.append(f"    FOREIGN KEY ({fk_columns}) REFERENCES {referred_table} ({referred_columns})")

        # 将列定义添加到建表语句中
        create_table_statement += ",\n".join(column_definitions)
        create_table_statement += "\n);"

        # 添加索引定义
        for index in indexes:
            if not index['unique']:
                index_columns = ", ".join(index['column_names'])
                create_table_statement += f"\nCREATE INDEX {index['name']} ON {table_name} ({index_columns});"
            else:
                index_columns = ", ".join(index['column_names'])
                create_table_statement += f"\nCREATE UNIQUE INDEX {index['name']} ON {table_name} ({index_columns});"

        # 将建表语句存储到字典中
        creation_statements[table_name] = create_table_statement

    return creation_statements


def get_table_creation_statements_2():
    creation_statements = {}
    with engine.connect() as connection:
        # 获取所有表名
        table_names = inspect(engine).get_table_names()
        for table_name in table_names:
            # 使用 SHOW CREATE TABLE 获取建表语句
            query = text(f"SHOW CREATE TABLE {table_name}")
            result = connection.execute(query).fetchone()
            if result:
                # 结果中的第二列是建表语句
                create_table_statement = result[1]
                creation_statements[table_name] = create_table_statement
    return creation_statements


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

