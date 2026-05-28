import json
import os
import sys

# Ensure backend directory is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.main import app

def export_openapi():
    # Generate the OpenAPI schema from the FastAPI instance
    openapi_schema = app.openapi()
    
    # Ensure target directory exists
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../docs/backend'))
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, 'openapi.json')
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
        
    print(f"[Success] OpenAPI schema exported successfully to: {output_path}")

if __name__ == "__main__":
    export_openapi()
