import json
import pytest
from unittest.mock import MagicMock, patch
from saladbox.tools.system_control import SystemControlTool
from saladbox.tools.network import NetworkTool
from saladbox.tools.local_db import LocalDbTool

@pytest.mark.asyncio
async def test_system_control_tool():
    tool = SystemControlTool()
    
    # Mock _run_osa to simulate AppleScript output
    with patch.object(tool, "_run_osa") as mock_osa:
        mock_osa.return_value = (0, "50")
        
        # Test get volume
        res = await tool.execute("volume")
        assert "Current system volume is: 50%" in res
        mock_osa.assert_called_with("output volume of (get volume settings)")
        
        # Test set volume
        mock_osa.return_value = (0, "")
        res = await tool.execute("volume", value="80")
        assert "Successfully set system volume to 80%" in res
        mock_osa.assert_called_with("set volume output volume 80")
        
        # Test mute status
        mock_osa.return_value = (0, "true")
        res = await tool.execute("mute", value="status")
        assert "System mute is currently: ON" in res
        
        # Test notify
        mock_osa.return_value = (0, "")
        res = await tool.execute("notify", message="Hello World")
        assert "displayed successfully" in res

@pytest.mark.asyncio
async def test_network_tool():
    tool = NetworkTool()
    
    # Test ping with mocked subprocess
    with patch("subprocess.run") as mock_run:
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Ping success output"
        mock_run.return_value = mock_res
        
        res = await tool.execute("ping", host="localhost")
        assert "Ping Results for localhost" in res
        assert "Ping success output" in res

    # Test ip_info with mocked HTTP session response
    with patch("aiohttp.ClientSession.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status = 200
        async def mock_json():
            return {
                "ip": "1.2.3.4",
                "city": "Dallas",
                "country": "US",
                "org": "Mock ISP"
            }
        mock_resp.json = mock_json
        
        # Setup context manager
        mock_context = MagicMock()
        async def __aenter__(self):
            return mock_resp
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        mock_context.__aenter__ = __aenter__
        mock_context.__aexit__ = __aexit__
        mock_get.return_value = mock_context
        
        res = await tool.execute("ip_info")
        assert "Public IP Information" in res
        assert "1.2.3.4" in res
        assert "Dallas" in res
        assert "Mock ISP" in res

@pytest.mark.asyncio
async def test_local_db_tool():
    tool = LocalDbTool()
    
    # Use a temporary database for testing to avoid overriding production sandbox.db
    tool.db_path = "data/test_sandbox.db"
    if os.path.exists(tool.db_path):
        os.remove(tool.db_path)
        
    try:
        # 1. Create table
        schema = "id INTEGER PRIMARY KEY, name TEXT, value REAL"
        create_res = await tool.execute("create_table", table_name="test_table", schema=schema)
        assert "created successfully" in create_res
        
        # 2. Insert record
        data = {"id": 1, "name": "Test Key", "value": 99.5}
        insert_res = await tool.execute("insert", table_name="test_table", data=json.dumps(data))
        assert "Successfully inserted" in insert_res
        
        # 3. Query record
        query_res = await tool.execute("query", sql="SELECT * FROM test_table")
        assert "Columns: id, name, value" in query_res
        assert "Test Key" in query_res
        
        # 4. List tables
        list_res = await tool.execute("list_tables")
        assert "test_table" in list_res
        
    finally:
        # Cleanup test DB
        if os.path.exists(tool.db_path):
            os.remove(tool.db_path)
            
import os
