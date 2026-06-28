"""Sandbox SQLite Local Database tool for custom data storage."""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any
from saladbox.tools.base import BaseTool


class LocalDbTool(BaseTool):
    """Manage structured sandboxed data inside a local SQLite database."""

    def __init__(self):
        super().__init__()
        os.makedirs("data", exist_ok=True)
        self.db_path = "data/sandbox.db"

    @property
    def name(self) -> str:
        return "local_db"

    @property
    def description(self) -> str:
        return (
            "Manage local structured data inside a sandboxed SQLite database. Actions: "
            "'create_table' (create a table with a schema definition), "
            "'insert' (insert data record as JSON key-value pairs), "
            "'query' (execute a read-only SQL query), "
            "'list_tables' (list all tables and their columns)."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create_table", "insert", "query", "list_tables"],
                    "description": "Database action to perform",
                },
                "table_name": {
                    "type": "string",
                    "description": "Name of the table (required for 'create_table' and 'insert')",
                },
                "schema": {
                    "type": "string",
                    "description": "Columns schema definition, e.g. 'id INTEGER PRIMARY KEY, name TEXT, score REAL'",
                },
                "data": {
                    "type": "string",
                    "description": "JSON string of key-value pairs representing the record(s) to insert",
                },
                "sql": {
                    "type": "string",
                    "description": "Read-only SQL query to execute (required for 'query')",
                },
            },
            "required": ["action"],
        }

    async def execute(
        self,
        action: str,
        table_name: str = "",
        schema: str = "",
        data: str = "",
        sql: str = "",
    ) -> str:
        if action == "list_tables":
            return self._list_tables()
        elif action == "create_table":
            if not table_name or not schema:
                return "Error: 'table_name' and 'schema' are required for 'create_table'."
            return self._create_table(table_name, schema)
        elif action == "insert":
            if not table_name or not data:
                return "Error: 'table_name' and 'data' are required for 'insert'."
            return self._insert(table_name, data)
        elif action == "query":
            if not sql:
                return "Error: 'sql' is required for the 'query' action."
            return self._query(sql)
        return f"Unknown action: {action}"

    def _create_table(self, table_name: str, schema: str) -> str:
        # Basic validation on table name
        if not table_name.isalnum() and "_" not in table_name:
            return "Error: Invalid table name. Use alphanumeric characters and underscores only."

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            query = f"CREATE TABLE IF NOT EXISTS {table_name} ({schema})"
            cursor.execute(query)
            conn.commit()
            return f"Table '{table_name}' created successfully (or already existed)."
        except Exception as e:
            return f"Error creating table: {e}"
        finally:
            conn.close()

    def _insert(self, table_name: str, data_str: str) -> str:
        if not table_name.isalnum() and "_" not in table_name:
            return "Error: Invalid table name."

        try:
            record = json.loads(data_str)
            if not isinstance(record, dict):
                return "Error: Data must represent a JSON object/dictionary."
        except Exception as e:
            return f"Error parsing JSON data: {e}"

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            columns = ", ".join(record.keys())
            placeholders = ", ".join(["?"] * len(record))
            values = tuple(record.values())
            
            query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
            cursor.execute(query, values)
            conn.commit()
            return f"Successfully inserted record into '{table_name}'."
        except Exception as e:
            return f"Error inserting record: {e}"
        finally:
            conn.close()

    def _query(self, sql: str) -> str:
        # Validate read-only SELECT or WITH queries
        sql_clean = sql.strip().upper()
        if not (sql_clean.startswith("SELECT") or sql_clean.startswith("WITH")):
            return "Error: Only read-only SELECT queries are allowed."

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute(sql)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            
            if not rows:
                return "Query returned 0 rows."

            # Format result
            output = [f"Columns: {', '.join(columns)}\n"]
            for row in rows[:50]: # Limit to 50 results in output text
                output.append(str(row))
            
            if len(rows) > 50:
                output.append(f"\n... and {len(rows) - 50} more rows (output truncated)")
                
            return "\n".join(output)
        except Exception as e:
            return f"Error executing query: {e}"
        finally:
            conn.close()

    def _list_tables(self) -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [t[0] for t in cursor.fetchall()]
            if not tables:
                return "No custom tables found in the database."

            output = ["**Sandbox Database Tables:**"]
            for table in tables:
                cursor.execute(f"PRAGMA table_info({table})")
                cols = [f"{col[1]} ({col[2]})" for col in cursor.fetchall()]
                output.append(f"- **{table}**: {', '.join(cols)}")
                
            return "\n".join(output)
        except Exception as e:
            return f"Error listing tables: {e}"
        finally:
            conn.close()
