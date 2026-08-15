import logging
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    filename=os.path.join(BASE_DIR, "server.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=8000,
        log_config=None,
        access_log=False,
    )
