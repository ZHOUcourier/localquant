"""LocalQuant 启动入口"""
import uvicorn
from backend.config import settings


def main():
    uvicorn.run(
        "backend.main:app",
        host="127.0.0.1",
        port=settings.backend_port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
