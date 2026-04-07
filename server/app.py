import sys
import os

# Ensure Python can find the 'backend' folder located in the parent directory
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from backend.app import app
import uvicorn

def main():
    uvicorn.run(app, host="0.0.0.0", port=7860)

if __name__ == "__main__":
    main()
