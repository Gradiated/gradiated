"""Exercise the deployed reader bootstrap SQL on disposable local PostgreSQL."""
import os
from pathlib import Path
import subprocess
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'infra/environments/prod/us-east-1/kubernetes/workloads/metabase/postgres-reader.yaml'


class MetabaseReaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        host = os.environ.get('DOCKER_HOST') or subprocess.check_output(
            ['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'], text=True
        ).strip()
        if not host.startswith('unix://'):
            raise RuntimeError('These tests require a local Docker socket')
        cls.docker = ['docker', '--host', host]
        cls.container = 'metabase-reader-test-' + uuid.uuid4().hex[:12]
        subprocess.run(cls.docker + ['run', '-d', '--name', cls.container, '--network', 'none',
            '-e', 'POSTGRES_PASSWORD=test-only', 'postgres:17.10-alpine3.23'],
            check=True, capture_output=True, timeout=90)
        cls.addClassCleanup(lambda: subprocess.run(cls.docker + ['rm', '-f', '-v', cls.container],
            capture_output=True, timeout=30))
        for _ in range(100):
            r = subprocess.run(cls.docker + ['exec', cls.container, 'pg_isready', '-h', '127.0.0.1'],
                capture_output=True, timeout=5)
            if r.returncode == 0:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError('PostgreSQL readiness timed out')
        cls.sql("""
            CREATE ROLE gradiated_app;
            CREATE ROLE metabase_reader LOGIN;
            GRANT ALL ON SCHEMA public TO gradiated_app;
            SET ROLE gradiated_app;
            CREATE TABLE accounts (secret text);
            CREATE TABLE sessions (secret text);
            CREATE TABLE verifications (secret text);
            CREATE TABLE api_keys (secret text);
            CREATE TABLE users (id int);
            CREATE TABLE organizations (id int);
            CREATE TABLE balance_transactions (id int);
            CREATE TABLE custom_analytics (id int);
            CREATE VIEW custom_report AS SELECT * FROM custom_analytics;
            GRANT SELECT ON ALL TABLES IN SCHEMA public TO metabase_reader;
            ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO metabase_reader;
        """)
        text = MANIFEST.read_text()
        cls.bootstrap = text.split("<<'SQL'\n", 1)[1].split('\n              SQL', 1)[0]
        cls.sql(cls.bootstrap)
        cls.sql(cls.bootstrap)

    @classmethod
    def sql(cls, statement, check=True):
        return subprocess.run(cls.docker + ['exec', '-i', cls.container, 'psql', '-U', 'postgres',
            '-v', 'ON_ERROR_STOP=1', '-v', 'admin_username=postgres', '-v', 'application_owner=gradiated_app',
            '-v', 'reader_username=metabase_reader', '-v', 'reader_password=test-only', '-At'],
            input=statement, text=True, capture_output=True, check=check, timeout=15)

    def test_credentials_are_inaccessible(self):
        for table in ['accounts', 'sessions', 'verifications', 'api_keys']:
            with self.subTest(table=table):
                result = self.sql(f'SET ROLE metabase_reader; SELECT * FROM {table};', check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('permission denied', result.stderr)

    def test_analytics_remain_read_only(self):
        self.sql('SET ROLE metabase_reader; SELECT * FROM users; SELECT * FROM organizations; SELECT * FROM balance_transactions; SELECT * FROM custom_analytics; SELECT * FROM custom_report;')
        for statement in ['INSERT INTO users VALUES (1)', 'DELETE FROM users', 'TRUNCATE balance_transactions', 'CREATE TABLE forbidden (id int)']:
            with self.subTest(statement=statement):
                self.assertNotEqual(self.sql('SET ROLE metabase_reader; ' + statement, check=False).returncode, 0)

    def test_new_tables_are_readable_after_sync(self):
        self.sql('SET ROLE gradiated_app; CREATE TABLE new_analytics (id int);')
        result = self.sql('SET ROLE metabase_reader; SELECT * FROM new_analytics;', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.sql(self.bootstrap)
        self.sql('SET ROLE metabase_reader; SELECT * FROM new_analytics;')

    def test_recreated_credentials_stay_private(self):
        self.sql('SET ROLE gradiated_app; DROP TABLE sessions; CREATE TABLE sessions (secret text);')
        for sync in [False, True]:
            with self.subTest(after_sync=sync):
                if sync:
                    self.sql(self.bootstrap)
                result = self.sql('SET ROLE metabase_reader; SELECT * FROM sessions;', check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('permission denied', result.stderr)

    def test_application_owner_still_writes(self):
        self.sql("SET ROLE gradiated_app; INSERT INTO accounts VALUES ('synthetic'); DELETE FROM accounts;")


if __name__ == '__main__':
    unittest.main()
