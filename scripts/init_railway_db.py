#!/usr/bin/env python3
"""
Initialize Railway database with schema and pgvector extension.
Run this from the Railway environment where ACTIVEKG_DSN is available.
"""
import os
import sys
import psycopg

def main():
    dsn = os.environ.get('ACTIVEKG_DSN') or os.environ.get('DATABASE_URL')
    if not dsn:
        print("ERROR: ACTIVEKG_DSN or DATABASE_URL environment variable not set")
        sys.exit(1)

    print(f"Connecting to database...")

    try:
        # Connect to database
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                # Check if pgvector is available
                print("Checking pgvector extension availability...")
                cur.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'vector';")
                if not cur.fetchone():
                    print("ERROR: pgvector extension is not available in this PostgreSQL instance")
                    print("Railway's default PostgreSQL doesn't include pgvector.")
                    print("\nPlease deploy a PostgreSQL instance with pgvector:")
                    print("1. Remove the current Postgres service")
                    print("2. Add a new service from the 'pgvector/pgvector:pg16' Docker image")
                    print("3. Set environment variables: POSTGRES_USER=activekg, POSTGRES_PASSWORD=<password>, POSTGRES_DB=activekg")
                    sys.exit(1)

                print("✓ pgvector extension is available")

                # Enable extensions
                print("Creating extensions...")
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
                print("✓ Extensions created")

                # Check if schema is already initialized
                cur.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'nodes';")
                if cur.fetchone():
                    print("✓ Database schema already initialized")
                    sys.exit(0)

                # Read and execute init.sql
                print("Initializing database schema...")
                init_sql_path = os.path.join(os.path.dirname(__file__), '..', 'db', 'init.sql')
                with open(init_sql_path, 'r') as f:
                    sql = f.read()

                # Execute schema creation
                cur.execute(sql)
                print("✓ Database schema initialized")

                # Check if RLS policies file exists
                rls_sql_path = os.path.join(os.path.dirname(__file__), '..', 'enable_rls_policies.sql')
                if os.path.exists(rls_sql_path):
                    print("Applying RLS policies...")
                    with open(rls_sql_path, 'r') as f:
                        sql = f.read()
                    cur.execute(sql)
                    print("✓ RLS policies applied")

                # Check if text search migration exists
                text_search_path = os.path.join(os.path.dirname(__file__), '..', 'db', 'migrations', 'add_text_search.sql')
                if os.path.exists(text_search_path):
                    print("Applying text search migration...")
                    with open(text_search_path, 'r') as f:
                        sql = f.read()
                    cur.execute(sql)
                    print("✓ Text search migration applied")

                print("\n✅ Database initialization complete!")

    except Exception as e:
        print(f"ERROR: Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
