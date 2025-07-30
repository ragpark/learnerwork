# LMS Content Push MVP
# A FastAPI-based service for selectively pushing learner content using xAPI standards

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timezone
import uuid
import json
import httpx
import asyncio
import os
import re
from dataclasses import dataclass, asdict
from enum import Enum
import logging
from sqlalchemy import create_engine, Column, String, DateTime, JSON, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./lms_push.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
class ContentPushRecord(Base):
    __tablename__ = "content_push_records"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    learner_id = Column(String, nullable=False)
    content_id = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    xapi_statement = Column(JSON, nullable=False)
    destination = Column(String, nullable=False)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    pushed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

class FilterRule(Base):
    __tablename__ = "filter_rules"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    content_types = Column(JSON, nullable=False)  # List of allowed content types
    grade_threshold = Column(String, nullable=True)  # Minimum grade
    tags_required = Column(JSON, nullable=True)  # Required tags
    learner_groups = Column(JSON, nullable=True)  # Specific learner groups
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Pydantic Models
class ContentType(str, Enum):
    ESSAY = "essay"
    VIDEO = "video"
    AUDIO = "audio"
    PRESENTATION = "presentation"
    CODE = "code"
    QUIZ = "quiz"
    PROJECT = "project"

class LearnerContent(BaseModel):
    learner_id: str
    learner_name: str
    learner_email: str
    content_id: str
    content_type: ContentType
    title: str
    description: Optional[str] = None
    content_url: str
    submission_date: datetime
    grade: Optional[str] = None
    tags: List[str] = []
    metadata: Dict[str, Any] = {}

class FilterCriteria(BaseModel):
    content_types: List[ContentType] = []
    min_grade: Optional[str] = None
    required_tags: List[str] = []
    learner_groups: List[str] = []

class DestinationConfig(BaseModel):
    name: str
    type: str  # "lrs", "webhook", "s3", etc.
    endpoint: str
    auth_token: Optional[str] = None
    additional_config: Dict[str, Any] = {}

class PushRequest(BaseModel):
    content: LearnerContent
    destination: str
    force_push: bool = False

class DrivePlatform(str, Enum):
    GOOGLE_DRIVE = "google_drive"
    ONE_DRIVE = "one_drive"

class DrivePushRequest(BaseModel):
    file_url: str
    platform: DrivePlatform
    content: LearnerContent
    destination: str
    force_push: bool = False

def convert_drive_link(url: str, platform: DrivePlatform) -> str:
    """Convert shared drive link to direct download link."""
    if platform == DrivePlatform.GOOGLE_DRIVE:
        match = re.search(r"/d/([\w-]+)", url)
        if match:
            file_id = match.group(1)
            return f"https://drive.google.com/uc?export=download&id={file_id}"
    elif platform == DrivePlatform.ONE_DRIVE:
        if "download=1" not in url:
            separator = "&" if "?" in url else "?"
            return url + separator + "download=1"
    return url

class XAPIStatement(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: Dict[str, Any]
    verb: Dict[str, Any]
    object: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None

# xAPI Statement Builder
class XAPIBuilder:
    @staticmethod
    def create_statement(content: LearnerContent, action: str = "completed") -> XAPIStatement:
        """Create xAPI statement from learner content"""
        
        actor = {
            "mbox": f"mailto:{content.learner_email}",
            "name": content.learner_name,
            "objectType": "Agent"
        }
        
        verb_map = {
            "completed": {
                "id": "http://adlnet.gov/expapi/verbs/completed",
                "display": {"en-US": "completed"}
            },
            "submitted": {
                "id": "http://adlnet.gov/expapi/verbs/answered", 
                "display": {"en-US": "submitted"}
            }
        }
        
        verb = verb_map.get(action, verb_map["completed"])
        
        obj = {
            "id": f"http://lms.example.com/content/{content.content_id}",
            "definition": {
                "name": {"en-US": content.title},
                "description": {"en-US": content.description or ""},
                "type": f"http://adlnet.gov/expapi/activities/{content.content_type.value}"
            },
            "objectType": "Activity"
        }
        
        result = None
        if content.grade:
            result = {
                "score": {"raw": content.grade},
                "completion": True,
                "success": True
            }
        
        context = {
            "instructor": {"name": "LMS System", "objectType": "Agent"},
            "platform": "LMS Platform",
            "language": "en-US",
            "extensions": {
                "http://lms.example.com/content_type": content.content_type.value,
                "http://lms.example.com/tags": content.tags,
                "http://lms.example.com/metadata": content.metadata
            }
        }
        
        return XAPIStatement(
            actor=actor,
            verb=verb,
            object=obj,
            result=result,
            context=context
        )

# Content Filter Engine
class ContentFilter:
    def __init__(self, db: Session):
        self.db = db
    
    def should_push(self, content: LearnerContent, rule_id: Optional[str] = None) -> tuple[bool, str]:
        """Determine if content should be pushed based on filter rules"""
        
        if rule_id:
            rule = self.db.query(FilterRule).filter(FilterRule.id == rule_id).first()
            if not rule:
                return False, "Filter rule not found"
            rules = [rule]
        else:
            rules = self.db.query(FilterRule).filter(FilterRule.is_active == True).all()
        
        if not rules:
            return True, "No active filter rules - allowing all content"
        
        for rule in rules:
            if self._matches_rule(content, rule):
                return True, f"Matches rule: {rule.name}"
        
        return False, "Content does not match any filter rules"
    
    def _matches_rule(self, content: LearnerContent, rule: FilterRule) -> bool:
        """Check if content matches a specific filter rule"""
        
        # Check content type
        if rule.content_types and content.content_type.value not in rule.content_types:
            return False
        
        # Check grade threshold (simplified - assumes letter grades)
        if rule.grade_threshold and content.grade:
            grade_values = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
            threshold_val = grade_values.get(rule.grade_threshold, 0)
            content_val = grade_values.get(content.grade.upper(), 0)
            if content_val < threshold_val:
                return False
        
        # Check required tags
        if rule.tags_required:
            if not all(tag in content.tags for tag in rule.tags_required):
                return False
        
        # Check learner groups (would need additional learner metadata in real implementation)
        if rule.learner_groups:
            # Placeholder - in real implementation, check learner group membership
            pass
        
        return True

# Destination Adapters
class BaseDestinationAdapter:
    def __init__(self, config: DestinationConfig):
        self.config = config
    
    async def push_content(self, statement: XAPIStatement, content: LearnerContent) -> Dict[str, Any]:
        raise NotImplementedError

class LRSAdapter(BaseDestinationAdapter):
    """Learning Record Store adapter for xAPI statements"""
    
    async def push_content(self, statement: XAPIStatement, content: LearnerContent) -> Dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "X-Experience-API-Version": "1.0.3"
        }
        
        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.config.endpoint}/statements",
                json=statement.dict(),
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code not in [200, 201, 204]:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"LRS push failed: {response.text}"
                )
            
            return {"status": "success", "lrs_response": response.json() if response.text else {}}

class WebhookAdapter(BaseDestinationAdapter):
    """Generic webhook adapter"""
    
    async def push_content(self, statement: XAPIStatement, content: LearnerContent) -> Dict[str, Any]:
        payload = {
            "xapi_statement": statement.dict(),
            "content_metadata": content.dict(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        headers = {"Content-Type": "application/json"}
        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.config.endpoint,
                json=payload,
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code not in [200, 201, 202]:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Webhook push failed: {response.text}"
                )
            
            return {"status": "success", "webhook_response": response.json() if response.text else {}}

# Destination Factory
class DestinationFactory:
    adapters = {
        "lrs": LRSAdapter,
        "webhook": WebhookAdapter
    }
    
    @classmethod
    def create_adapter(cls, config: DestinationConfig) -> BaseDestinationAdapter:
        adapter_class = cls.adapters.get(config.type)
        if not adapter_class:
            raise ValueError(f"Unknown destination type: {config.type}")
        return adapter_class(config)

# FastAPI App
app = FastAPI(
    title="LMS Content Push Service",
    description="Selective content pushing with xAPI standards",
    version="1.0.0"
)

# Test Interface HTML (embedded for easy deployment)
TEST_INTERFACE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LMS Content Push - Test Interface</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; background: rgba(255, 255, 255, 0.95); border-radius: 20px; box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1); overflow: hidden; }
        .header { background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%); color: white; padding: 30px; text-align: center; }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; font-weight: 300; }
        .header p { opacity: 0.9; font-size: 1.1em; }
        .main-content { padding: 30px; }
        .auth-section { background: linear-gradient(135deg, #ffeaa7 0%, #fab1a0 100%); padding: 20px; border-radius: 15px; margin-bottom: 30px; }
        .auth-section h3 { color: #2d3436; margin-bottom: 15px; }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: 600; color: #333; }
        input, select, textarea { width: 100%; padding: 12px 15px; border: 2px solid #e0e0e0; border-radius: 10px; font-size: 14px; transition: all 0.3s ease; }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #667eea; box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1); }
        .btn { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 12px 25px; border-radius: 10px; cursor: pointer; font-size: 16px; font-weight: 600; transition: all 0.3s ease; margin-right: 10px; margin-bottom: 10px; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4); }
        .btn-secondary { background: linear-gradient(135deg, #95a5a6 0%, #7f8c8d 100%); }
        .response-box { background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 10px; padding: 20px; margin-top: 20px; font-family: 'Courier New', monospace; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
        .card { background: white; border-radius: 15px; padding: 25px; margin-bottom: 20px; box-shadow: 0 5px 15px rgba(0, 0, 0, 0.08); border: 1px solid #f0f0f0; }
        .card h3 { color: #2c3e50; margin-bottom: 15px; font-size: 1.3em; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎓 LMS Content Push Service</h1>
            <p>Test Interface for xAPI-based Learning Content Distribution</p>
        </div>
        <div class="main-content">
            <div class="auth-section">
                <h3>🔐 API Configuration</h3>
                <div class="form-row">
                    <div class="form-group">
                        <label for="apiUrl">API Base URL</label>
                        <input type="url" id="apiUrl" value="" placeholder="Auto-detected">
                    </div>
                    <div class="form-group">
                        <label for="apiToken">API Token</label>
                        <input type="password" id="apiToken" value="dev-token-123" placeholder="Your API token">
                    </div>
                </div>
                <button class="btn" onclick="testConnection()">Test Connection</button>
                <div id="connectionStatus"></div>
            </div>
            
            <div class="card">
                <h3>📝 Quick Test</h3>
                <form id="quickTestForm">
                    <div class="form-row">
                        <div class="form-group">
                            <label for="learnerName">Student Name</label>
                            <input type="text" id="learnerName" value="Test Student" required>
                        </div>
                        <div class="form-group">
                            <label for="contentTitle">Assignment Title</label>
                            <input type="text" id="contentTitle" value="Sample Assignment" required>
                        </div>
                    </div>
                    <div class="form-row">
                        <div class="form-group">
                            <label for="contentType">Content Type</label>
                            <select id="contentType" required>
                                <option value="essay">Essay</option>
                                <option value="video">Video</option>
                                <option value="presentation">Presentation</option>
                                <option value="project">Project</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="grade">Grade</label>
                            <select id="grade">
                                <option value="A">A</option>
                                <option value="B">B</option>
                                <option value="C">C</option>
                            </select>
                        </div>
                    </div>
                    <button type="submit" class="btn">🚀 Push Content</button>
                    <button type="button" class="btn btn-secondary" onclick="generateSample()">🎲 Generate Sample</button>
                </form>
                <div id="response" class="response-box" style="display: none;"></div>
            </div>
        </div>
    </div>
    
    <script>
        // Auto-detect API URL based on current location
        document.getElementById('apiUrl').value = window.location.origin;
        
        function getHeaders() {
            return {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${document.getElementById('apiToken').value}`
            };
        }
        
        async function testConnection() {
            const status = document.getElementById('connectionStatus');
            status.innerHTML = '<p>Testing...</p>';
            
            try {
                const response = await fetch('/health');
                const data = await response.json();
                status.innerHTML = `<p style="color: green;">✅ Connected! Status: ${data.status}</p>`;
            } catch (error) {
                status.innerHTML = `<p style="color: red;">❌ Connection failed: ${error.message}</p>`;
            }
        }
        
        function generateSample() {
            const samples = [
                { name: "Alice Johnson", title: "AI Ethics in Healthcare", type: "essay", grade: "A" },
                { name: "Bob Chen", title: "Climate Change Presentation", type: "presentation", grade: "B" },
                { name: "Carol Martinez", title: "Portfolio Website", type: "project", grade: "A" }
            ];
            
            const sample = samples[Math.floor(Math.random() * samples.length)];
            document.getElementById('learnerName').value = sample.name;
            document.getElementById('contentTitle').value = sample.title;
            document.getElementById('contentType').value = sample.type;
            document.getElementById('grade').value = sample.grade;
        }
        
        document.getElementById('quickTestForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const contentData = {
                content: {
                    learner_id: 'test_' + Date.now(),
                    learner_name: document.getElementById('learnerName').value,
                    learner_email: `${document.getElementById('learnerName').value.toLowerCase().replace(' ', '.')}@university.edu`,
                    content_id: 'test_content_' + Date.now(),
                    content_type: document.getElementById('contentType').value,
                    title: document.getElementById('contentTitle').value,
                    description: 'Test submission via web interface',
                    content_url: 'https://example.com/test.pdf',
                    submission_date: new Date().toISOString(),
                    grade: document.getElementById('grade').value,
                    tags: ['test', 'web-interface'],
                    metadata: { source: 'test-interface' }
                },
                destination: 'main_lrs',
                force_push: true
            };
            
            const responseDiv = document.getElementById('response');
            responseDiv.style.display = 'block';
            responseDiv.textContent = 'Pushing content...';
            
            try {
                const response = await fetch('/push-content', {
                    method: 'POST',
                    headers: getHeaders(),
                    body: JSON.stringify(contentData)
                });
                
                const result = await response.json();
                responseDiv.textContent = JSON.stringify(result, null, 2);
            } catch (error) {
                responseDiv.textContent = `Error: ${error.message}`;
            }
        });
        
        // Test connection on load
        testConnection();
        generateSample();
    </script>
</body>
</html>"""

security = HTTPBearer()

# Configuration (in production, use proper config management)
DESTINATIONS = {
    "main_lrs": DestinationConfig(
        name="Main LRS",
        type="lrs",
        endpoint=os.getenv("LRS_ENDPOINT", "https://lrs.example.com/xapi"),
        auth_token=os.getenv("LRS_TOKEN")
    ),
    "analytics_webhook": DestinationConfig(
        name="Analytics Webhook",
        type="webhook", 
        endpoint=os.getenv("WEBHOOK_ENDPOINT", "https://analytics.example.com/webhook"),
        auth_token=os.getenv("WEBHOOK_TOKEN")
    )
}

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Simple auth check (replace with proper auth in production)
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    expected_token = os.getenv("API_TOKEN", "dev-token-123")
    if credentials.credentials != expected_token:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    return credentials.credentials

# API Endpoints
@app.get("/")
async def root():
    return {"message": "LMS Content Push Service", "version": "1.0.0"}

@app.get("/test", response_class=HTMLResponse)
async def get_test_interface():
    """Serve the HTML test interface"""
    return TEST_INTERFACE_HTML

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}

@app.post("/push-content")
async def push_content(
    request: PushRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    token: str = Depends(verify_token)
):
    """Push learner content to specified destination"""
    
    # Check if destination exists
    if request.destination not in DESTINATIONS:
        raise HTTPException(status_code=400, detail=f"Unknown destination: {request.destination}")
    
    # Check filter rules
    content_filter = ContentFilter(db)
    should_push, reason = content_filter.should_push(request.content)
    
    if not should_push and not request.force_push:
        raise HTTPException(status_code=403, detail=f"Content filtered: {reason}")
    
    # Create xAPI statement
    statement = XAPIBuilder.create_statement(request.content)
    
    # Create push record
    push_record = ContentPushRecord(
        learner_id=request.content.learner_id,
        content_id=request.content.content_id,
        content_type=request.content.content_type.value,
        xapi_statement=statement.dict(),
        destination=request.destination,
        status="pending"
    )
    db.add(push_record)
    db.commit()
    
    # Schedule background push
    background_tasks.add_task(
        execute_push, 
        push_record.id, 
        statement, 
        request.content, 
        request.destination
    )
    
    return {
        "message": "Content push initiated",
        "push_id": push_record.id,
        "statement_id": statement.id,
        "filter_reason": reason
    }

@app.post("/push-from-drive")
async def push_from_drive(
    request: DrivePushRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    token: str = Depends(verify_token)
):
    """Push content referenced by a Google Drive or OneDrive link."""

    direct_url = convert_drive_link(request.file_url, request.platform)
    request.content.content_url = direct_url

    # Reuse the existing push logic
    push_req = PushRequest(
        content=request.content,
        destination=request.destination,
        force_push=request.force_push,
    )

    return await push_content(
        push_req,
        background_tasks,
        db,
        token,
    )

async def execute_push(push_id: str, statement: XAPIStatement, content: LearnerContent, destination: str):
    """Execute the actual push in background"""
    db = SessionLocal()
    try:
        push_record = db.query(ContentPushRecord).filter(ContentPushRecord.id == push_id).first()
        
        # Get destination config and create adapter
        dest_config = DESTINATIONS[destination]
        adapter = DestinationFactory.create_adapter(dest_config)
        
        # Execute push
        result = await adapter.push_content(statement, content)
        
        # Update record
        push_record.status = "success"
        push_record.pushed_at = datetime.utcnow()
        
        logger.info(f"Successfully pushed content {content.content_id} to {destination}")
        
    except Exception as e:
        push_record.status = "failed"
        push_record.error_message = str(e)
        logger.error(f"Failed to push content {content.content_id}: {e}")
    
    finally:
        db.commit()
        db.close()

@app.get("/push-status/{push_id}")
async def get_push_status(
    push_id: str,
    db: Session = Depends(get_db),
    token: str = Depends(verify_token)
):
    """Get status of a content push"""
    record = db.query(ContentPushRecord).filter(ContentPushRecord.id == push_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Push record not found")
    
    return {
        "id": record.id,
        "status": record.status,
        "created_at": record.created_at,
        "pushed_at": record.pushed_at,
        "error_message": record.error_message
    }

@app.post("/filter-rules")
async def create_filter_rule(
    rule_data: dict,
    db: Session = Depends(get_db),
    token: str = Depends(verify_token)
):
    """Create a new content filter rule"""
    rule = FilterRule(
        name=rule_data["name"],
        content_types=rule_data.get("content_types", []),
        grade_threshold=rule_data.get("grade_threshold"),
        tags_required=rule_data.get("tags_required"),
        learner_groups=rule_data.get("learner_groups")
    )
    db.add(rule)
    db.commit()
    
    return {"message": "Filter rule created", "rule_id": rule.id}

@app.get("/filter-rules")
async def list_filter_rules(
    db: Session = Depends(get_db),
    token: str = Depends(verify_token)
):
    """List all filter rules"""
    rules = db.query(FilterRule).all()
    return [
        {
            "id": rule.id,
            "name": rule.name,
            "content_types": rule.content_types,
            "grade_threshold": rule.grade_threshold,
            "tags_required": rule.tags_required,
            "is_active": rule.is_active
        }
        for rule in rules
    ]

@app.post("/test-filter")
async def test_filter(
    content: LearnerContent,
    rule_id: Optional[str] = None,
    db: Session = Depends(get_db),
    token: str = Depends(verify_token)
):
    """Test if content would pass filter rules"""
    content_filter = ContentFilter(db)
    should_push, reason = content_filter.should_push(content, rule_id)
    
    return {
        "should_push": should_push,
        "reason": reason,
        "content_summary": {
            "type": content.content_type,
            "grade": content.grade,
            "tags": content.tags
        }
    }

@app.get("/destinations")
async def list_destinations(token: str = Depends(verify_token)):
    """List available destinations"""
    return {
        name: {
            "name": config.name,
            "type": config.type,
            "endpoint": config.endpoint
        }
        for name, config in DESTINATIONS.items()
    }

# WebSocket endpoint for real-time push status (optional)
from fastapi import WebSocket, WebSocketDisconnect

@app.websocket("/ws/push-status/{push_id}")
async def websocket_push_status(websocket: WebSocket, push_id: str):
    await websocket.accept()
    db = SessionLocal()
    
    try:
        while True:
            record = db.query(ContentPushRecord).filter(ContentPushRecord.id == push_id).first()
            if record:
                await websocket.send_json({
                    "status": record.status,
                    "updated_at": record.pushed_at.isoformat() if record.pushed_at else None
                })
                
                if record.status in ["success", "failed"]:
                    break
            
            await asyncio.sleep(1)
    
    except WebSocketDisconnect:
        pass
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
