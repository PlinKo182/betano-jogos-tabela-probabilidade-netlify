import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()


@app.get("/api/{path:path}")
async def proxy(request: Request, path: str):
    # Forward request to FastAPI application
    response = await app.handle_request(request.scope, receive=request.receive)
    return JSONResponse(content=response.body, status_code=response.status_code)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3000)
