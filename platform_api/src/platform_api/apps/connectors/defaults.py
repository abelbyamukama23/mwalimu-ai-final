"""Default catalog definitions for platform connectors."""

import uuid

DEFAULT_CONNECTORS = [
    {
        "id": uuid.UUID("a1111111-1111-4111-8111-111111111111"),
        "name": "Web Crawler",
        "slug": "web-crawler",
        "description": "Crawls and synchronizes documentation pages, websites, and guides directly into your library.",
        "connector_type": "web_crawler",
        "auth_type": "none",
        "config_schema": {
            "type": "object",
            "properties": {
                "base_url": {
                    "type": "string",
                    "title": "Base URL",
                    "description": "Root documentation or website URL to crawl (e.g. https://docs.example.com)."
                },
                "max_pages": {
                    "type": "integer",
                    "title": "Max Pages",
                    "description": "Maximum number of pages to crawl and index (1-50).",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50
                },
                "allowed_domains": {
                    "type": "string",
                    "title": "Allowed Domains",
                    "description": "Optional comma-separated list of additional allowed domains."
                }
            },
            "required": ["base_url"]
        },
        "auth_schema": {
            "type": "object",
            "properties": {
                "api_key": {
                    "type": "string",
                    "title": "API Key / Bearer Token",
                    "description": "Optional authorization token for protected documentation.",
                    "writeOnly": True
                }
            }
        },
        "is_active": True,
    },
    {
        "id": uuid.UUID("b2222222-2222-4222-8222-222222222222"),
        "name": "Google Drive",
        "slug": "google-drive",
        "description": "Synchronize documents, PDF files, and presentations from shared or private Google Drive folders.",
        "connector_type": "google_drive",
        "auth_type": "oauth2",
        "config_schema": {
            "type": "object",
            "properties": {
                "folder_id": {
                    "type": "string",
                    "title": "Folder ID",
                    "description": "Google Drive folder ID containing documents to index."
                }
            },
            "required": ["folder_id"]
        },
        "auth_schema": {
            "type": "object",
            "properties": {
                "oauth_token": {
                    "type": "string",
                    "title": "OAuth 2.0 Access Token",
                    "description": "Google Drive OAuth 2.0 access token.",
                    "writeOnly": True
                }
            },
            "required": ["oauth_token"]
        },
        "is_active": True,
    },
    {
        "id": uuid.UUID("c3333333-3333-4333-8333-333333333333"),
        "name": "Notion",
        "slug": "notion",
        "description": "Synchronize Notion pages, team workspaces, and databases directly into your knowledge base.",
        "connector_type": "notion",
        "auth_type": "api_key",
        "config_schema": {
            "type": "object",
            "properties": {
                "database_id": {
                    "type": "string",
                    "title": "Database / Page ID",
                    "description": "Notion Database ID or root Page ID to synchronize."
                }
            },
            "required": ["database_id"]
        },
        "auth_schema": {
            "type": "object",
            "properties": {
                "api_key": {
                    "type": "string",
                    "title": "Internal Integration Secret",
                    "description": "Notion integration secret token starting with secret_...",
                    "writeOnly": True
                }
            },
            "required": ["api_key"]
        },
        "is_active": True,
    },
    {
        "id": uuid.UUID("d4444444-4444-4444-8444-444444444444"),
        "name": "Amazon S3",
        "slug": "amazon-s3",
        "description": "Ingest and synchronize documents, PDFs, and text objects from an AWS S3 bucket.",
        "connector_type": "s3",
        "auth_type": "basic_auth",
        "config_schema": {
            "type": "object",
            "properties": {
                "bucket_name": {
                    "type": "string",
                    "title": "S3 Bucket Name",
                    "description": "Target Amazon S3 bucket name."
                },
                "prefix": {
                    "type": "string",
                    "title": "Folder Prefix",
                    "description": "Optional object key prefix (e.g. documents/)."
                },
                "region": {
                    "type": "string",
                    "title": "AWS Region",
                    "description": "AWS Region (e.g. us-east-1, eu-west-1).",
                    "default": "us-east-1"
                }
            },
            "required": ["bucket_name"]
        },
        "auth_schema": {
            "type": "object",
            "properties": {
                "aws_access_key_id": {
                    "type": "string",
                    "title": "AWS Access Key ID"
                },
                "aws_secret_access_key": {
                    "type": "string",
                    "title": "AWS Secret Access Key",
                    "writeOnly": True
                }
            },
            "required": ["aws_access_key_id", "aws_secret_access_key"]
        },
        "is_active": True,
    },
    {
        "id": uuid.UUID("e5555555-5555-4555-8555-555555555555"),
        "name": "File System",
        "slug": "file-system",
        "description": "Synchronize documents and directories from a mounted file system.",
        "connector_type": "file_system",
        "auth_type": "none",
        "config_schema": {
            "type": "object",
            "properties": {
                "mount_path": {
                    "type": "string",
                    "title": "Mount Directory Path",
                    "description": "Path to the directory containing files to index."
                }
            },
            "required": ["mount_path"]
        },
        "auth_schema": {
            "type": "object",
            "properties": {}
        },
        "is_active": True,
    },
]
