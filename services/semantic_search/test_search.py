"""Test script for semantic search service."""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from clients.semantic_search_client import SemanticSearchClient


async def test_service():
    """Test the semantic search service."""
    
    print("=" * 60)
    print("SEMANTIC SEARCH SERVICE TEST")
    print("=" * 60)
    
    # Initialize client
    client = SemanticSearchClient(base_url="http://nuc-1.local:42110")
    
    try:
        # Test 1: Health Check
        print("\n1. Health Check")
        print("-" * 60)
        is_healthy = await client.health_check()
        print(f"Service healthy: {is_healthy}")
        
        if not is_healthy:
            print("❌ Service is not healthy. Aborting tests.")
            return
            
        # Test 2: Get Stats
        print("\n2. Index Statistics")
        print("-" * 60)
        stats = await client.get_stats()
        print(f"Documents: {stats.get('documents', 'N/A')}")
        print(f"Brain path: {stats.get('brain_path', 'N/A')}")
        print(f"Embedding model: {stats.get('embedding_model', 'N/A')}")
        print(f"File watching: {stats.get('file_watching', 'N/A')}")
        
        # Test 3: Simple Search
        print("\n3. Simple Search Query")
        print("-" * 60)
        query = "sync verification test"
        print(f"Query: '{query}'")
        results = await client.search(query, limit=3)
        print(f"Results: {len(results)}")
        
        for i, result in enumerate(results, 1):
            print(f"\nResult {i}:")
            print(f"  File: {result.file}")
            print(f"  Score: {result.score:.3f}")
            print(f"  Snippet: {result.entry[:100]}...")
            
        # Test 4: Folder-Specific Search
        print("\n4. Folder-Specific Search")
        print("-" * 60)
        query = "daily log"
        folder = "journal"
        print(f"Query: '{query}' in folder '{folder}'")
        results = await client.search_by_folder(query, folder)
        print(f"Results: {len(results)}")
        
        for i, result in enumerate(results, 1):
            print(f"\nResult {i}:")
            print(f"  File: {result.file}")
            print(f"  Score: {result.score:.3f}")
            
        # Test 5: Trigger Reindex
        print("\n5. Trigger Full Reindex")
        print("-" * 60)
        await client.trigger_reindex(force=True)
        print("✓ Reindex triggered (background task)")
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_service())
