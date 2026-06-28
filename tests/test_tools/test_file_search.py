import os
import tempfile
import pytest
from saladbox.tools.file_search import FileSearchTool

@pytest.mark.asyncio
async def test_file_search_tool():
    # Setup temporary directory and files
    with tempfile.TemporaryDirectory() as temp_dir:
        file1 = os.path.join(temp_dir, "test1.txt")
        file2 = os.path.join(temp_dir, "test2.py")
        file3 = os.path.join(temp_dir, "binary.bin")
        
        # Text file 1
        with open(file1, "w", encoding="utf-8") as f:
            f.write("This is a simple text file.\nIt contains a keyword: banana.\nHope this works!")
            
        # Text file 2 (Python file)
        with open(file2, "w", encoding="utf-8") as f:
            f.write("def test_function():\n    print('apple and orange')\n")
            
        # Binary file (should be skipped)
        with open(file3, "wb") as f:
            f.write(b"\x00\x01\x02binary content\x00")
            
        tool = FileSearchTool()
        
        # 1. Run Indexing
        index_res = await tool.execute(action="index", directory=temp_dir)
        assert "Indexing Completed" in index_res
        assert "New/Updated files indexed: 2" in index_res # test1.txt and test2.py

        # 2. Run Status check
        status_res = await tool.execute(action="status")
        assert "Total Files Indexed: " in status_res
        
        # 3. Search for keyword in file 1
        search_res1 = await tool.execute(action="search", query="banana")
        assert "test1.txt" in search_res1
        assert "Line 2: It contains a keyword: banana." in search_res1
        
        # 4. Search for keyword in file 2
        search_res2 = await tool.execute(action="search", query="apple")
        assert "test2.py" in search_res2
        assert "Line 2: print('apple and orange')" in search_res2
        
        # 5. Search for non-existent keyword
        search_res3 = await tool.execute(action="search", query="nonexistentkeyword")
        assert "No results found" in search_res3
