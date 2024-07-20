from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import time
import random
import uuid
from pydantic import BaseModel
 
app = FastAPI()
 
origins = [
    "http://127.0.0.1:5500",
    "http://127.0.0.1:8000",
    "http://localhost:5500",
    'http://localhost:3000',
    "http://ec2-3-107-70-86.ap-southeast-2.compute.amazonaws.com"
]
 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


responses = {}

# 기존 키의 존재 여부를 확인하면서 값을 추가하는 함수
# uuid 존재 여부 확인 후에 response 값 추가 (중복 클릭 방지)
def add_to_dict(dict, key, value):
    if key not in dict:
        dict[key] = value

# 유저 Connection 관리 및 uuid 부여, Broadcast 기능
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        self.active_connections[connection_id] = websocket
        print(f"New connection: {connection_id}")
        return connection_id

    def disconnect(self, connection_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
            print(f"Disconnected: {connection_id}")

    async def broadcast(self, message: dict):
        disconnected = []
        for connection_id, connection in self.active_connections.items():
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Error sending message to {connection_id}: {e}")
                disconnected.append(connection_id)
        for connection_id in disconnected:
            self.disconnect(connection_id)

manager = ConnectionManager()
 
class Timer:
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.duration = None
        self.timer_task = None
        self.responses = {}
 
    def start(self, duration: float):
        if self.start_time is not None:
            raise HTTPException(status_code=400, detail="Timer is already running")
        self.start_time = time.time()
        self.end_time = None
        self.duration = duration
        self.responses = {}
 
    def stop(self):
        if self.start_time is None:
            raise HTTPException(status_code=400, detail="Timer is not running")
        self.end_time = time.time()
        if self.timer_task:
            self.timer_task.cancel()
 
    def reset(self):
        self.start_time = None
        self.end_time = None
        self.duration = None
        self.responses = {}
        if self.timer_task:
            self.timer_task.cancel()
 
    # def elapsed(self):
    #     if self.start_time is None:
    #         raise HTTPException(status_code=400, detail="Timer has not been started")
    #     if self.end_time is None:
    #         raise HTTPException(status_code=400, detail="Timer has not been stopped")
    #     return self.end_time - self.start_time
 
    def time_left(self):
        if self.start_time is None:
            raise HTTPException(status_code=400, detail="Timer has not been started")
        if self.duration is None:
            raise HTTPException(status_code=400, detail="No duration set for the timer")
        elapsed_time = time.time() - self.start_time
        remaining_time = self.duration - elapsed_time
        if remaining_time <= 0:
            return 0
        return remaining_time
 
    def status(self):
        return {
            "is_running": self.start_time is not None and self.end_time is None,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "time_left": self.time_left() if self.start_time is not None else None,
        }
 
    # async def countdown(self, websocket: WebSocket):
    #     try:
    #         if self.duration is None:
    #             raise HTTPException(status_code=400, detail="No duration set for the timer")
    #         await asyncio.sleep(self.duration)
    #         await websocket.send_text("Time's up! Please submit your response.")
    #         await self.collect_responses(websocket)
    #     except asyncio.CancelledError:
    #         await websocket.send_text("Timer reset or cancelled")
 
    # async def collect_responses(self, websocket: WebSocket):
    #     start_time = time.time()
    #     while time.time() - start_time < 60:
    #         if len(self.responses) >= 2:
    #             break
    #         await asyncio.sleep(1)
        
    #     if len(self.responses) < 2:
    #         await websocket.send_text("Timeout: Not all responses received.")
    #     else:
    #         result = self.evaluate_responses()
    #         await websocket.send_text(f"Result: {result}")
    #         if result:
    #             await websocket.send_text("Both responses are True. Starting 5-minute timer.")
    #             await self.start_five_min_timer(websocket)
    #         else:
    #             await websocket.send_text("Responses are not valid. Redirecting to survey page.")
 
    def evaluate_responses(self):
        response1 = self.responses.get("customer1", "False") == "True"
        response2 = self.responses.get("customer2", "False") == "True"
        return response1 and response2
 
    async def start_five_min_timer(self, websocket: WebSocket):
        try:
            self.start(300)  # 5 minutes
            await asyncio.sleep(300)
            await websocket.send_text("5-minute timer finished.")
        except asyncio.CancelledError:
            await websocket.send_text("5-minute timer reset or cancelled")
 
# Sample list of items
items = ["apple", "banana", "cherry", "date", "elderberry", "fig", "grape", "honeydew"]
 
@app.get("/random-items")
async def get_random_items():
    if len(items) < 3:
        raise HTTPException(status_code=400, detail="Not enough items in the list to select 3 unique items")
    selected_items = random.sample(items, 3)
    return {"selected_items": selected_items}
 
@app.websocket("/ws/random-items")
async def websocket_random_items(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.receive_text()  # Wait for client request
            if len(items) < 3:
                await websocket.send_json({"error": "Not enough items in the list to select 3 unique items"})
            else:
                selected_items = random.sample(items, 3)
                await websocket.send_json({"selected_items": selected_items})
    except WebSocketDisconnect:
        print("random-items WebSocket disconnected")
 
timer = Timer()
 
 
class TimerRequest(BaseModel):
    duration: float
 
@app.get("/")
async def read_root():
    return {"message": "Hello World"}
 
@app.post("/timer/start")
async def start_timer(timer_request: TimerRequest = None ,duration: float = None, background_tasks: BackgroundTasks = None, websocket: WebSocket = None):
    if timer_request:
        duration = timer_request.duration
    if duration == None or duration <= 0:
        raise HTTPException(status_code=400, detail="Invalid duration")
    timer.start(duration)
    timer.timer_task = asyncio.create_task(timer.countdown(websocket))
    return {"message": "Timer started", "duration": duration}
 
@app.post("/timer/stop")
async def stop_timer():
    timer.stop()
    return {"message": "Timer stopped"}
 
@app.post("/timer/reset")
async def reset_timer():
    responses = []
    timer.reset()
    return {"message": "Timer reset"}
 
@app.get("/timer/elapsed")
async def get_elapsed_time():
    return {
        "timer": timer.elapsed() if timer.start_time else "Not started"
    }
 
@app.get("/timer/status")
async def get_timer_status():
    return {
        "timer": timer.status()
    }
 
@app.get("/timer/time_left")
async def get_time_left():
    print("time_left 요청 메시지 받음")
    return {
        "timer": timer.time_left() if timer.start_time else "Not started"
    }
 
@app.websocket("/ws/timer")
async def websocket_timer(websocket: WebSocket):
    
    connection_id = await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            print("어떤 data를 받았는 지",connection_id, data)
            action = data.get("action")
            # duration = data.get("duration")
            await manager.broadcast(data)
            
            if action == "start":
                print("ws로 start 메시지 받음", connection_id, data)
            elif action == 'reset':
                print("websocket으로 reset 메시지 받음", connection_id, data)
            elif action == 'true' or action == 'false':
                # responses.append([connection_id, data])
                print("responses 초기화 전", responses)
                add_to_dict(responses, connection_id, action)    
                print("responses 만들어보자 후", responses)
                if len(responses) >= 2:
                    if all(value == 'true' for value in responses.values()):
                        print("모두 true", responses)
                        await manager.broadcast("All True")
                    else:
                        print("하나라도 false", responses)
                    responses.clear()
            elif action == 'init':
                print("websocket으로 reset 메시지 받음", connection_id, data)
                responses.clear()
            else :
                print("ws로 else 메시지 받음", connection_id, data)
            print("message 다시 돌려 보냄")
    except WebSocketDisconnect:
        manager.disconnect(connection_id)
        print(f"WebSocket {connection_id} disconnected")
 
# @app.websocket("/ws/response")
# async def websocket_response(websocket: WebSocket):
#     await websocket.accept()
#     try:
#         while True:
#             data = await websocket.receive_text()
#             customer_id, response = data.split(":")
#             timer.responses[customer_id] = response
#             if len(timer.responses) == 2:
#                 break
#     except WebSocketDisconnect:
#         print("response WebSocket disconnected")
#     finally:
#         response1 = timer.responses.get("customer1", "False") == "True"
#         response2 = timer.responses.get("customer2", "False") == "True"
#         result = response1 and response2
#         await websocket.send_json({"result": result})
