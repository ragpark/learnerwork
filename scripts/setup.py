"""
Database setup and sample data script
"""
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path to import main modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import Base, FilterRule, ContentPushRecord

def setup_database():
    """Initialize database with sample data"""
    database_url = os.getenv("DATABASE_URL", "sqlite:///./lms_push.db")
    
    # Handle Railway PostgreSQL URL format
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    engine = create_engine(database_url)
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")
    
    # Add sample filter rules
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    
    # Check if rules already exist
    existing_rules = db.query(FilterRule).count()
    
    if existing_rules == 0:
        sample_rules = [
            FilterRule(
                name="High Quality Essays",
                content_types=["essay"],
                grade_threshold="B",
                tags_required=["reviewed"],
                is_active=True
            ),
            FilterRule(
                name="All Video Content",
                content_types=["video"],
                is_active=True
            ),
            FilterRule(
                name="Final Projects Only",
                content_types=["project"],
                tags_required=["final"],
                is_active=True
            ),
            FilterRule(
                name="Honors Student Work",
                content_types=["essay", "project", "presentation"],
                grade_threshold="A",
                tags_required=["honors"],
                is_active=True
            )
        ]
        
        for rule in sample_rules:
            db.add(rule)
        
        db.commit()
        print(f"✅ Added {len(sample_rules)} sample filter rules")
    else:
        print(f"ℹ️  Database already has {existing_rules} filter rules")
    
    db.close()
    print("✅ Database setup complete!")

if __name__ == '__main__':
    setup_database()
