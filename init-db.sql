-- Primary database initialization
CREATE EXTENSION IF NOT EXISTS vector;

-- Create schema for application data
CREATE SCHEMA IF NOT EXISTS hcrm;

-- Basic tables will be created via Alembic migrations
-- This file handles extensions and initial permissions only
