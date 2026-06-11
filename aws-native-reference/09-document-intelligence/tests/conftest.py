import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("EXTRACT_MODE", "demo")  # never call Bedrock in tests
