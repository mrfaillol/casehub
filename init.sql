-- ILC CaseHub - Database Initialization Script
-- This runs automatically when PostgreSQL container starts

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE casehub TO casehub;

-- Create schema if using separate schema
-- CREATE SCHEMA IF NOT EXISTS casehub;
-- GRANT ALL ON SCHEMA casehub TO casehub;

-- Note: Tables are created by SQLAlchemy on app startup
-- This file is for any custom initialization needed
