import time
from app.core.logger import logger


async def log_requests(request, call_next):
    start = time.time()
    # Log path and method only — never the request body
    logger.info(f"Request: {request.method} {request.url.path}")
    response = await call_next(request)
    duration = time.time() - start
    logger.info(f"method={request.method} path={request.url.path} status_code={response.status_code} duration={duration:.3f}s")
    return response
