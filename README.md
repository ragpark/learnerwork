# LMS Content Push MVP

A FastAPI-based service for selectively pushing learner content from your LMS to third-party destinations using industry standards like xAPI (Experience API).

## Features

- **xAPI Standard Compliance**: Generates standardized learning record statements
- **Flexible Content Filtering**: Rule-based system for selective content pushing  
- **Multiple Destinations**: Support for Learning Record Stores (LRS) and webhooks
- **Background Processing**: Asynchronous content delivery
- **Real-time Status**: WebSocket support for push status monitoring
- **Railway.app Ready**: Optimized for easy deployment

## Architecture

```
LMS → Content Push Service → [Filter Engine] → Destination Adapters → Third-party Systems
                                ↓
                          xAPI Statement Generation
```

## Quick Start

### 1. Local Development

```bash
# Clone the repository
git clone <your-repo-url>
cd lms-content-push

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp config/env.example .env
# Edit .env with your configuration

# Run with Docker Compose (recommended)
docker-compose up

# Or run directly
uvicorn lms-content-push.main:app --reload
```

### 2. Railway.app Deployment

1. **Connect GitHub Repository**
   - Link your GitHub repo to Railway
   - Railway will auto-detect the Dockerfile

2. **Configure Environment Variables**
   ```
   API_TOKEN=your-secure-token
   LRS_ENDPOINT=https://your-lrs.com/xapi  
   LRS_TOKEN=your-lrs-token
   WEBHOOK_ENDPOINT=https://your-webhook.com
   WEBHOOK_TOKEN=your-webhook-token
   ```

3. **Add Database**
   - Add PostgreSQL plugin in Railway dashboard
   - DATABASE_URL will be automatically set
   - If setting manually, use a full connection string such as:
     `postgresql://user:password@host:5432/database`

4. **Deploy**
   - Push to main branch triggers automatic deployment

## API Usage

### Authentication

All endpoints require a Bearer token:

```bash
curl -H "Authorization: Bearer your-api-token" \
     https://your-service.railway.app/destinations
```

### Push Content

```python
import requests

content_data = {
    "content": {
        "learner_id": "student123",
        "learner_name": "John Doe", 
        "learner_email": "john.doe@university.edu",
        "content_id": "essay001",
        "content_type": "essay",
        "title": "History of Computing",
        "description": "Final essay submission",
        "content_url": "https://lms.edu/content/essay001.pdf",
        "submission_date": "2024-07-30T10:30:00Z",
        "grade": "A",
        "tags": ["history", "technology", "final-project"],
        "metadata": {
            "course_id": "CS101",
            "assignment_id": "final_essay"
        }
    },
    "destination": "main_lrs",
    "force_push": false
}

response = requests.post(
    "https://your-service.railway.app/push-content",
    json=content_data,
    headers={"Authorization": "Bearer your-api-token"}
)

print(response.json())
# Returns: {"message": "Content push initiated", "push_id": "uuid", ...}
```

### Create Filter Rules

```python
filter_rule = {
    "name": "High Quality Content Only",
    "content_types": ["essay", "project", "presentation"],
    "grade_threshold": "B",  # Minimum grade
    "tags_required": ["reviewed"],
    "learner_groups": ["honors_students"]
}

response = requests.post(
    "https://your-service.railway.app/filter-rules",
    json=filter_rule,
    headers={"Authorization": "Bearer your-api-token"}
)
```

### Check Push Status

```python
push_id = "your-push-id-from-previous-call"
response = requests.get(
    f"https://your-service.railway.app/push-status/{push_id}",
    headers={"Authorization": "Bearer your-api-token"}
)

status = response.json()
print(f"Status: {status['status']}")
```

## Content Types Supported

- `essay` - Written assignments
- `video` - Video submissions  
- `audio` - Audio recordings
- `presentation` - Slide presentations
- `code` - Programming assignments
- `quiz` - Quiz responses
- `project` - Project portfolios

## Filter Rules

Create rules to selectively push content based on:

- **Content Types**: Only push specific types of content
- **Grade Thresholds**: Minimum grade requirements
- **Required Tags**: Content must have specific tags
- **Learner Groups**: Restrict to specific student cohorts

### Example Filter Scenarios

```python
# Only push A-grade essays with "portfolio" tag
{
    "name": "Portfolio Essays Only",
    "content_types": ["essay"],
    "grade_threshold": "A", 
    "tags_required": ["portfolio"]
}

# All video content for honors students
{
    "name": "Honors Video Content",
    "content_types": ["video"],
    "learner_groups": ["honors_students"]
}

# Final projects with any grade
{
    "name": "All Final Projects", 
    "content_types": ["project"],
    "tags_required": ["final"]
}
```

## Destination Configuration

### Learning Record Store (LRS)

```python
DESTINATIONS = {
    "main_lrs": {
        "name": "Main LRS",
        "type": "lrs",
        "endpoint": "https://lrs.example.com/xapi",
        "auth_token": "your-lrs-token"
    }
}
```

### Generic Webhook

```python
DESTINATIONS = {
    "analytics_webhook": {
        "name": "Analytics System",
        "type": "webhook",
        "endpoint": "https://analytics.example.com/webhook", 
        "auth_token": "your-webhook-token"
    }
}
```

## xAPI Statement Example

The service automatically generates xAPI statements like this:

```json
{
    "id": "uuid-here",
    "timestamp": "2024-07-30T10:30:00Z",
    "actor": {
        "mbox": "mailto:john.doe@university.edu",
        "name": "John Doe",
        "objectType": "Agent"
    },
    "verb": {
        "id": "http://adlnet.gov/expapi/verbs/completed",
        "display": {"en-US": "completed"}
    },
    "object": {
        "id": "http://lms.example.com/content/essay001",
        "definition": {
            "name": {"en-US": "History of Computing"},
            "description": {"en-US": "Final essay submission"},
            "type": "http://adlnet.gov/expapi/activities/essay"
        },
        "objectType": "Activity"
    },
    "result": {
        "score": {"raw": "A"},
        "completion": true,
        "success": true
    },
    "context": {
        "instructor": {"name": "LMS System", "objectType": "Agent"},
        "platform": "LMS Platform",
        "extensions": {
            "http://lms.example.com/content_type": "essay",
            "http://lms.example.com/tags": ["history", "technology"],
            "http://lms.example.com/metadata": {"course_id": "CS101"}
        }
    }
}
```

## LMS Integration Examples

### Canvas LMS Webhook

```python
from fastapi import Request

@app.post("/webhook/canvas")
async def canvas_webhook(request: Request):
    """Receive Canvas webhook and push to destinations"""
    payload = await request.json()
    
    # Transform Canvas data to LearnerContent format
    content = LearnerContent(
        learner_id=payload['user_id'],
        learner_name=payload['user_name'],
        learner_email=payload['user_email'],
        content_id=payload['assignment_id'],
        content_type=ContentType.ESSAY,  # Map based on assignment type
        title=payload['assignment_name'],
        content_url=payload['submission_url'],
        submission_date=payload['submitted_at'],
        grade=payload.get('grade'),
        tags=payload.get('tags', [])
    )
    
    # Push to configured destinations
    for dest in DESTINATIONS:
        await push_content(PushRequest(content=content, destination=dest))
```

### Moodle Integration

```python
import requests

def fetch_moodle_submissions():
    """Fetch recent submissions from Moodle API"""
    moodle_api = "https://your-moodle.edu/webservice/rest/server.php"
    
    params = {
        'wstoken': 'your-moodle-token',
        'wsfunction': 'mod_assign_get_submissions',
        'moodlewsrestformat': 'json'
    }
    
    response = requests.get(moodle_api, params=params)
    submissions = response.json()
    
    for submission in submissions:
        content = LearnerContent(
            learner_id=str(submission['userid']),
            content_id=str(submission['id']),
            # ... map other fields
        )
        
        # Push via our service
        push_to_service(content)
```

## Monitoring and Logging

### Health Check
```bash
curl https://your-service.railway.app/health
```

### WebSocket Status Monitoring
```javascript
const ws = new WebSocket('wss://your-service.railway.app/ws/push-status/push-id');
ws.onmessage = (event) => {
    const status = JSON.parse(event.data);
    console.log('Push status:', status.status);
};
```

### Database Queries
```python
# Check recent pushes
recent_pushes = db.query(ContentPushRecord)\
    .filter(ContentPushRecord.created_at > datetime.now() - timedelta(hours=24))\
    .all()

# Failed pushes
failed_pushes = db.query(ContentPushRecord)\
    .filter(ContentPushRecord.status == "failed")\
    .all()
```

## Security Considerations

1. **API Token Security**: Use strong, unique tokens for production
2. **HTTPS Only**: Ensure all communications use HTTPS
3. **Rate Limiting**: Implement rate limiting for production use
4. **Input Validation**: All content is validated via Pydantic models
5. **Error Handling**: Sensitive information is not exposed in error messages

## Extending the System

### Adding New Destination Types

```python
class S3Adapter(BaseDestinationAdapter):
    async def push_content(self, statement: XAPIStatement, content: LearnerContent):
        # Implementation for S3 storage
        pass

# Register in DestinationFactory
DestinationFactory.adapters["s3"] = S3Adapter
```

### Custom Content Filters

```python
class AdvancedContentFilter(ContentFilter):
    def _matches_rule(self, content: LearnerContent, rule: FilterRule) -> bool:
        # Add custom filtering logic
        if content.metadata.get('plagiarism_score', 0) > 0.3:
            return False
        return super()._matches_rule(content, rule)
```

## Troubleshooting

### Common Issues

1. **Connection Timeouts**: Check destination endpoint availability
2. **Authentication Errors**: Verify API tokens in environment variables  
3. **Database Errors**: Ensure DATABASE_URL is correctly set
4. **Filter Rejections**: Use `/test-filter` endpoint to debug rules

### Debug Mode

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
uvicorn lms-content-push.main:app --log-level debug
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License - see LICENSE file for details.
