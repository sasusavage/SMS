"""
NaCCA School Management System - Configuration
"""
import os
from datetime import timedelta

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'nacca-sms-secret-key-change-in-production'
    
    # PostgreSQL Database - fix postgres:// -> postgresql:// for SQLAlchemy
    _database_url = os.environ.get('DATABASE_URL', '')
    if _database_url.startswith('postgres://'):
        _database_url = _database_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _database_url or \
        'postgresql://postgres:nbaSavage123@localhost:5432/schooldb'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
    }
    
    # Session Configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # Upload Configuration
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf'}
    
    # PDF Generation
    PDF_TEMPLATE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'pdf')
    
    # NaCCA Specific Settings
    NACCA_GRADING_SCALE = {
        'PRIMARY': {
            (80, 100): ('1', 'Highest'),
            (70, 79): ('2', 'Higher'),
            (60, 69): ('3', 'High'),
            (50, 59): ('4', 'High Average'),
            (40, 49): ('5', 'Average'),
            (30, 39): ('6', 'Low Average'),
            (25, 29): ('7', 'Below Average'),
            (20, 24): ('8', 'Low'),
            (0, 19): ('9', 'Very Low'),
        },
        'JHS': {
            (80, 100): ('1', 'Excellent'),
            (70, 79): ('2', 'Very Good'),
            (60, 69): ('3', 'Good'),
            (55, 59): ('4', 'Credit'),
            (50, 54): ('5', 'Credit'),
            (45, 49): ('6', 'Credit'),
            (40, 44): ('7', 'Pass'),
            (35, 39): ('8', 'Pass'),
            (0, 34): ('9', 'Fail'),
        },
        'SHS': {
            (80, 100): ('A1', 'Excellent'),
            (70, 79): ('B2', 'Very Good'),
            (60, 69): ('B3', 'Good'),
            (55, 59): ('C4', 'Credit'),
            (50, 54): ('C5', 'Credit'),
            (45, 49): ('C6', 'Credit'),
            (40, 44): ('D7', 'Pass'),
            (35, 39): ('E8', 'Pass'),
            (0, 34): ('F9', 'Fail'),
        }
    }
    
    # Academic Terms
    TERMS = ['First Term', 'Second Term', 'Third Term']
    
    # School Levels
    SCHOOL_LEVELS = ['Creche', 'Nursery', 'Kindergarten', 'Primary', 'JHS', 'SHS']


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    
    # Override with environment variables in production
    SECRET_KEY = os.environ.get('SECRET_KEY')
    
    # Fix for Coolify/Heroku: postgres:// -> postgresql://
    _db_url = os.environ.get('DATABASE_URL', '')
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'postgresql://postgres:password@localhost:5432/nacca_sms_test'


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
