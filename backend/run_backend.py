from uvicorn import run
from main import app
 
if __name__ == "__main__":
	run(app, host="127.0.0.1", port=8000, log_level="info") 