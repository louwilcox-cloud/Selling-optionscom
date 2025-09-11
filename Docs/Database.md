Migration Document: Syncing Replit PostgreSQL Database to EC2 Docker PostgreSQLPurpose: This document outlines the process to export a PostgreSQL database from a Replit project and import it into a PostgreSQL database running in a Docker container on an EC2 instance, ensuring identical schema and data for the "Selling-Options.com" application. It assumes the source (Replit) has the correct database state and the target (EC2) needs to match it exactly. The process includes exporting the DB, transferring it, importing it, and verifying the setup, with steps to handle common issues like foreign key constraints and password authentication.Prerequisites:Replit: Access to the Replit project with a PostgreSQL database (hosted remotely by Replit, accessible via DATABASE_URL environment variable). Tools psql and pg_dump (PostgreSQL 16.9) are pre-installed.
EC2: An Amazon Linux 2 EC2 instance with Docker running a PostgreSQL container (image: postgres:16, named selling-options-db, port 5432 internal). The container uses user postgres and password password (as per database.py).
EC2 Tools: PostgreSQL client tools (psql, pg_dump) installed. If not, install with:bash

sudo yum update -y
sudo yum install -y postgresql

Verify: pg_dump --version && psql --version (should show PostgreSQL 9.2 or higher; 9.2 worked despite version mismatch).
Access: Shell access to Replit and SSH access to EC2. Ability to copy files (e.g., via copy-paste or SCP).
Database: Small database (<10MB) with tables users, watchlists, admin_users, user_sessions. Schema includes foreign keys (FKs) and sequences.

Steps:Dump the Replit DatabaseIn the Replit shell, confirm the DATABASE_URL (contains host, user, password, port, DB name):bash

echo $DATABASE_URL

Example output (redact sensitive parts): postgresql://postgres:REDACTED@some-host.replit.com:5432/options_db
Export the full database (schema + data) to a file:bash

pg_dump $DATABASE_URL > replit_dump.sql

Verify the file exists and is non-empty:bash

ls -l replit_dump.sql
cat replit_dump.sql

Note: The dump includes tables (users, watchlists, admin_users, user_sessions), sequences, constraints, and data. Expect admin_users to have rows (e.g., user_id 1, 2, 3, 6) but users may be empty or have matching IDs. If errors (e.g., connection refused), ensure DATABASE_URL is set in Replit’s secrets panel.

Transfer the Dump to EC2Copy the replit_dump.sql content (from cat output) to your local machine (e.g., via copy-paste or download from Replit).
On EC2 (via SSH), create the file:bash

vi replit_dump.sql

Press i, paste the full dump, ensure tabs in COPY sections (e.g., admin_users data like 1\t2025-09-04 20:11:37.764424), press Esc, then :wq to save.

Verify:bash

cat replit_dump.sql

Alternative: Use SCP to transfer the file from Replit to EC2 if direct copy is easier:bash

scp replit_dump.sql ec2-user@<EC2-PUBLIC-IP>:/home/ec2-user/

Backup the Current EC2 DatabaseConfirm the Docker container is running:bash

docker ps

Look for selling-options-db (postgres:16, port 5432 internal).
Dump the current EC2 database as a safety backup:bash

docker exec -e PGPASSWORD=password -t selling-options-db pg_dump -U postgres options_db > ec2_backup.sql

Verify:bash

ls -l ec2_backup.sql

Drop and Recreate the EC2 DatabaseDrop the existing options_db:bash

docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d postgres -c "DROP DATABASE options_db;"

Expected output: DROP DATABASE (if it doesn’t exist, no error).
Create a fresh options_db:bash

docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d postgres -c "CREATE DATABASE options_db;"

Expected output: CREATE DATABASE

Import the Replit Dump into EC2Import the dump:bash

docker exec -i -e PGPASSWORD=password selling-options-db psql -U postgres -d options_db < replit_dump.sql

Expected: No output (silent success). If errors (e.g., FK violations due to admin_users referencing non-existent users), edit replit_dump.sql before import to add:sql

SET session_replication_role = replica;

at the start and:sql

SET session_replication_role = DEFAULT;

before the dump complete line. Then retry the import.

Fix Foreign Key Constraints (if needed)If admin_users FK (admin_users_user_id_fkey) is missing or causes errors:bash

docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "DELETE FROM public.admin_users;"
docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "ALTER TABLE public.admin_users ADD CONSTRAINT admin_users_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;"

Re-insert admin_users data (example from Replit):bash

docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "INSERT INTO public.admin_users (user_id, granted_at) VALUES (1, '2025-09-04 20:11:37.764424');"
docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "INSERT INTO public.admin_users (user_id, granted_at) VALUES (2, '2025-09-07 23:36:45.898056');"
docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "INSERT INTO public.admin_users (user_id, granted_at) VALUES (3, '2025-09-05 12:34:18.576005');"
docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "INSERT INTO public.admin_users (user_id, granted_at) VALUES (6, '2025-09-07 16:11:13.712103');"

Sync User Data (if not empty in Replit)Check Replit users table:bash

psql $DATABASE_URL -c "SELECT * FROM public.users;"

If rows exist, insert them into EC2 with exact values (example from Replit):bash

docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "INSERT INTO public.users (id, email, password_hash, created_at, last_login, is_active, login_count) VALUES (2, 'twilcox811@gmail.com', '\$2b\$12\$EXTvre2srEQrRr.RAXVFtuMgpDywRs4L91oBaePIsYHCSAUa2H.Xq', '2025-09-04 20:27:21.912853', '2025-09-05 14:26:43.744339', true, 21);"
docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "INSERT INTO public.users (id, email, password_hash, created_at, last_login, is_active, login_count) VALUES (1, 'lou.wilcox@gmail.com', '\$2b\$12\$NHHsNYgxzGQPshY0SLUF2O1hFlBoLYqVGEsFI6IH9.8sPZiHXEJmq', '2025-09-04 20:09:46.11136', '2025-09-06 19:06:28.837352', true, 45);"
docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "INSERT INTO public.users (id, email, password_hash, created_at, last_login, is_active, login_count) VALUES (6, 'admin@selling-options.com', '\$2b\$12\$sZEAXSIVTelCnIl6sKIgeONa3OeXPLwfQ0D.PrR0CDQskNMy52agK', '2025-09-07 14:38:26.083534', NULL, true, 0);"
docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "INSERT INTO public.users (id, email, password_hash, created_at, last_login, is_active, login_count) VALUES (3, 'admin@lab.com', '\$2b\$12\$nEstcau1g0KPJME/fqeQkOT..VqFxrjXPR6c24vGA2mYCcZ3rGvkO', '2025-09-05 12:34:12.999652', '2025-09-05 12:34:56.760991', true, 2);"

Note: Replace password hashes with '$2b$12$91MwWsPBXZWy7I/uWKwM7eQGnFsCBcOT8hehdbJgnT2.A2VJRQn/O' if you want to use plain password "password" for testing.

Verify the ImportDump the EC2 database:bash

docker exec -e PGPASSWORD=password -t selling-options-db pg_dump -U postgres options_db > final_ec2_dump.sql

Compare with replit_dump.sql:bash

cat final_ec2_dump.sql

Check key tables:bash

docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "SELECT * FROM public.users;"
docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "SELECT * FROM public.admin_users;"
docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "SELECT * FROM public.watchlists;"
docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "SELECT * FROM public.user_sessions;"

Test the ApplicationLog in with:Email: lou.wilcox@gmail.com, Password: password (if hash updated).
Email: admin@ez.com, Password: password (if added).

Test admin features (e.g., via /api/auth-status or app UI).
Create a test watchlist:bash

docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "INSERT INTO public.watchlists (name, symbols, created_by) VALUES ('Test Watchlist', 'AAPL,TSLA', 1);"

If login fails, check:App logs (e.g., docker logs selling-options-app).
Environment variables in docker-compose.yml or app config (ensure PGHOST, PGDATABASE, PGUSER, PGPASSWORD, PGPORT match: localhost, options_db, postgres, password, 5432).
Flask session config in api.py (session handling may cause issues).

Troubleshooting Tips:Connection Errors: If pg_dump or psql fail on Replit, verify DATABASE_URL in Replit’s secrets. On EC2, ensure the Docker container is running (docker ps) and port 5432 is accessible.
FK Violations: If import fails due to admin_users referencing non-existent users, use SET session_replication_role = replica; in the dump or clear admin_users before adding the FK.
Password Issues: If login fails, update passwords to known bcrypt hash ($2b$12$91MwWsPBXZWy7I/uWKwM7eQGnFsCBcOT8hehdbJgnT2.A2VJRQn/O for "password") or use the app’s password reset feature.
Schema Mismatch: If app expects username in users (per database.py), add it via:bash

docker exec -e PGPASSWORD=password -t selling-options-db psql -U postgres -d options_db -c "ALTER TABLE public.users ADD COLUMN username VARCHAR(50) UNIQUE;"

Version Mismatch: EC2’s pg_dump (9.2) worked with PostgreSQL 16.10, but if issues arise, upgrade:bash

sudo yum remove postgresql
sudo amazon-linux-extras install postgresql14

Post-Migration:Clean up: rm replit_dump.sql ec2_backup.sql final_ec2_dump.sql
Monitor app logs: docker logs selling-options-app
Automate future migrations using a script (e.g., bash script combining above commands).
For production, secure PGPASSWORD (use Docker secrets or AWS Secrets Manager) and ensure backups are stored (e.g., S3).

Notes:This process was tested on September 11, 2025, with a small database (<10 rows). For larger DBs, consider pg_dump --data-only for incremental updates.
If Replit data changes, repeat steps 1-8.
Ensure production EC2 has the same Docker setup (postgres:16, same env vars).

End of DocumentFeedback and Next StepsSave This: Copy this document to a file (e.g., migration_guide.md) and store it in your project repo or a safe place. It’s designed to be self-contained for a future helper.
Production Move: For your production EC2, follow the exact steps above after setting up the Docker container (postgres:16, same env vars). If the production environment differs (e.g., different DB password or host), let me know, and I’ll tweak the commands.
Verification: To be extra sure, run the verification commands (step 8) on your current EC2 to confirm everything’s stable, and test the app with lou.wilcox@gmail.com and password.
Anything Else: If you want to add test watchlists, secure the DB, or automate this (e.g., as a script), let me know!

